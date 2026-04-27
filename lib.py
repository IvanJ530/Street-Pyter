import pygame
from settings import *
from itertools import cycle, chain
from pygame.locals import *


def draw_hpbar(disp, player1, player2):
    # Health bar dimensions
    bar_height = 15
    bar_width = 300
    bar_y = 50  # Lowered by 100px
    border_width = 2
    
    # Player 1 health bar - moved 400px from left edge
    p1_x = 250
    p1_health = max(0, player1.health / TOTAL_HEALTH * bar_width)
    
    # Player 2 health bar - moved 400px from right edge
    p2_x = disp.get_width() - bar_width - 250
    p2_health = max(0, player2.health / TOTAL_HEALTH * bar_width)
    
    # Draw health bar borders
    pygame.draw.rect(disp, (255, 255, 255), pygame.Rect(p1_x - border_width, bar_y - border_width, bar_width + border_width*2, bar_height + border_width*2))
    pygame.draw.rect(disp, (255, 255, 255), pygame.Rect(p2_x - border_width, bar_y - border_width, bar_width + border_width*2, bar_height + border_width*2))
    
    # Draw health bar backgrounds
    pygame.draw.rect(disp, (0, 0, 0), pygame.Rect(p1_x, bar_y, bar_width, bar_height))
    pygame.draw.rect(disp, (0, 0, 0), pygame.Rect(p2_x, bar_y, bar_width, bar_height))
    
    # Draw health bars
    pygame.draw.rect(disp, (255, 0, 0), pygame.Rect(p1_x, bar_y, p1_health, bar_height))
    pygame.draw.rect(disp, (255, 0, 0), pygame.Rect(p2_x, bar_y, p2_health, bar_height))
    
    # Draw player names
    font = pygame.font.Font(None, 20)
    p1_name = font.render("P1", True, (255, 255, 255))
    p2_name = font.render("P2", True, (255, 255, 255))
    
    # Position names above health bars
    disp.blit(p1_name, (p1_x, bar_y - 20))
    disp.blit(p2_name, (p2_x, bar_y - 20))


# Delay specifies how many frames to delay between each new frame
def add_delay(frames, delay):
    # Creates a list with the right number of delays + the number of frames. Then slots the frames in between the delays
    result = [None for i in range(delay*len(frames) + len(frames))]
    result[::delay + 1] = frames
    return iter(result)


# Return sum of nested list
def nested_sum(array):
    return sum(sum(i) if isinstance(i, list) else i for i in array)


# Convert spritesheet to list of sprites
def parse_spritesheet(spritesheet, cellsize, columns, rows, scale):
    frames = []
    for y in range(rows):
        for x in range(columns):
            location = (x * cellsize[0], y * cellsize[1])
            sprite = pygame.transform.scale(spritesheet.subsurface(pygame.Rect(location, cellsize)), scale)
            # Must trim sprites to get rid of padding
            trimmed_sprite = pygame.Surface(sprite.get_bounding_rect().size, pygame.SRCALPHA)  # SRCALPHA makes background transparent
            trimmed_sprite.blit(sprite, (0,0))
            frames.append(trimmed_sprite)
    return frames

# In SF3, all characters have the same basic attacks, air attacks, crouch attacks, etc. Only the special moves differ. This class allows us create new characters
# much more easily, as only the animations are different between characters
class Character(pygame.sprite.Sprite):
    def __init__(self, flip, controller, size, opponent, disp, action_provider=None, home_x=None):
        self.size = size
        self.flip = flip
        self.controller = controller
        self.vel_y = 0
        self.vel_x = 0
        self.opponent = opponent
        self.disp = disp
        self.home_x = home_x

        self.action_provider = action_provider

        self.input_buffer = [None]
        self.frame_queue = None
        self.current_frame = None
        self.current_frame_index = None
        self.action = None  # [function, name, blit, extra, bounding_rect, args]
        self.last_attack = pygame.time.get_ticks()

        self.health = TOTAL_HEALTH
        self.ishit = False

        self.player = 0
        if controller:
            self.player = 1
        self.channel = pygame.mixer.Channel(self.player)

    # Animations are stored in a queue that gets evaluated every game loop
    def queue_add_frames(self, frames, force=False):
        if not self.frame_queue or force:
            self.frame_queue = frames

    # Some actions do not want to be reactivated if the key is held down, so we can compare the current input to the previous input to see if any keys are held down
    def keyboard_input(self, held=True):
        keys = pygame.key.get_pressed()
        # Use different key bindings based on which player this is
        if self.player == 0:  # Player 1
            inputs = [[keys[j] for j in i]for i in keyboard_binds]
        else:  # Player 2
            inputs = [[keys[j] for j in i]for i in keyboard_binds_p2]
            
        if not held:
            if self.input_buffer[-1] == inputs:
                return DEFAULT_INPUTS
        self.input_buffer.append(inputs)
        return inputs

    def controller_input(self, held=True):
        # By default we assume that there is no input
        controls = DEFAULT_INPUTS
        # Movement
        # Axis 1 - left joystick, up/down
        # AXis 2 - left joystick, left/right
        if self.controller.get_axis(1) < -TOLERANCE:
            controls[0][0] = True
        if self.controller.get_axis(1) > TOLERANCE:
            controls[0][1] = True
        if self.controller.get_axis(0) < -TOLERANCE:
            controls[0][2] = True
        if self.controller.get_axis(0) > TOLERANCE:
            controls[0][3] = True

        # Attack
        for count, i in enumerate(controller_binds):
            controls[1][count] = self.controller.get_button(i)

        # Compare input to previous input to get rid of held buttons
        if not held:
            if self.input_buffer[-1] == controls:
                return DEFAULT_INPUTS
        self.input_buffer.append(controls)
        return controls

    def external_action_input(self, held=True):
        # Pull the latest named action from the provider and convert it into
        # the same nested-list shape that keyboard/controller input produces.
        # Apply the same one-shot filter (held=False) as the other input paths
        # so taps don't auto-repeat across frames.
        from motion.named_action import named_to_input
        name = self.action_provider()
        inputs = named_to_input(name, flip=self.flip)

        if not held:
            if self.input_buffer[-1] == inputs:
                return DEFAULT_INPUTS
        self.input_buffer.append(inputs)
        return inputs

    # This function allows us to play the game without a controller, although the inputs will control both characters
    def get_input(self, held=True):
        if self.action_provider is not None:
            return self.external_action_input(held)
        if self.controller:
            return self.controller_input(held)
        else:
            return self.keyboard_input(held)

    def move(self, **_kwargs):
        dx = 0
        dy = 0

        # Decelerate knockback
        if self.vel_x != 0:
            if self.vel_x > 0:
                self.vel_x = max(0, self.vel_x - XGRAVITY)
            else:
                self.vel_x = min(0, self.vel_x + XGRAVITY)

        # Input-driven walk (only when not in an attack or hit animation)
        if not self.action:
            held = self.get_input()
            if held[0][2]:       # left
                dx = -SPEED
            elif held[0][3]:     # right
                dx = SPEED

        dx += self.vel_x
        self.vel_y += GRAVITY
        dy += self.vel_y

        # Screen boundaries
        if self.rect.left + dx < 0:
            dx = -self.rect.left
        if self.rect.right + dx > SCREEN_WIDTH:
            dx = SCREEN_WIDTH - self.rect.right
        if self.rect.bottom + dy > FLOOR:
            self.rect.bottom = FLOOR
            self.vel_y = 0
            dy = 0

        self.rect.x += dx
        self.rect.y += dy

    def attack(self, keys, *, mpunch_hbox, mpunch_kb, mpunch_st, mpunch_frames, mpunch_rect, mpunch_index, mpunch_dmg, mpunch_sfx,
               mkick_hbox, mkick_kb, mkick_st, mkick_frames, mkick_rect, mkick_index, mkick_dmg, mkick_sfx,
               hit_frame_final_index, **_ignored):

        if not self.action:
            blit = "bot"
            action = False
            if self.flip:
                blit = "right"
            end_frame_ = hit_frame_final_index

            # Any punch input → medium punch
            if any(keys[1][0:3]):
                self.frame_queue = mpunch_frames
                hbox_ = mpunch_hbox
                knockback_ = mpunch_kb
                dmg_ = mpunch_dmg
                rect = mpunch_rect
                stuntime_ = mpunch_st
                end_attack_ = mpunch_index
                self.channel.play(mpunch_sfx)
                action = True
            # Any kick input → medium kick
            elif any(keys[1][3:6]):
                self.frame_queue = mkick_frames
                hbox_ = mkick_hbox
                knockback_ = mkick_kb
                dmg_ = mkick_dmg
                rect = mkick_rect
                stuntime_ = mkick_st
                end_attack_ = mkick_index
                self.channel.play(mkick_sfx)
                action = True

            def basic_attack():
                hbox = hbox_
                knockback = knockback_
                dmg = dmg_
                stuntime = stuntime_
                end_frame = end_frame_
                end_attack = end_attack_
                spawn_rect = self.rect.topright
                if self.flip:
                    spawn_rect = [self.rect.topleft[0] - hbox[0], self.rect.topleft[1]]
                    knockback *= -1
                if self.current_frame_index == end_attack:
                    punch = pygame.Rect(spawn_rect, hbox)
                    if punch.colliderect(self.opponent.rect):
                        if self.action:
                            self.action[0] = lambda: None
                        self.opponent.hit(dmg, stuntime, knockback, end_frame)

            if action:
                self.action = [basic_attack, "basic_attack", blit, None, rect, None]

    def hit(self, dmg, stuntime, knockback, hit_frame_final_index):
        def stophit():
            if self.current_frame_index == hit_frame_final_index:
                self.ishit = False
                self.finish_action()
        def blockhit():
            if self.current_frame_index == hit_frame_final_index:
                self.finish_action()

        self.vel_x += knockback

        # Auto-block for motion-control players: idle (no attack in progress) = blocking.
        # Keyboard players block by pressing away from opponent (original behavior).
        can_block = False
        if self.action_provider is not None:
            can_block = (self.action is None)
        else:
            held_keys = self.get_input()
            move_away = held_keys[0][2]
            if self.flip:
                move_away = held_keys[0][3]
            can_block = move_away and not self.action

        if can_block:
            blocked_dmg = int(dmg * 0.3)
            self.health -= blocked_dmg
            if self.health < 0:
                self.health = 0
            self.ishit = False
            self.action = [blockhit, 'block', 'bot', None, None, None]
            self.queue_add_frames(chain(add_delay(self.block_frames, 4), iter([None for i in range(stuntime)])), force=True)
            return

        self.health -= dmg
        if self.health < 0:
            self.health = 0

        self.finish_action()
        self.action = [stophit, 'hit', 'bot', None, None, None]
        self.queue_add_frames((add_delay(self.hit_frames, stuntime)), force=True)
        self.ishit = True

    def update(self):
        # Flip players if on opposite sides
        if not self.controller:  # check if player 1
            if self.rect.centerx > self.opponent.rect.centerx:
                self.flip = True
                self.opponent.flip = False
            else:
                self.flip = False
                self.opponent.flip = True

        # Reset input buffer
        if len(self.input_buffer) > 10:
            self.input_buffer = self.input_buffer[:10]

        # Get next frame of the animation, if there is no frame go back to idling
        if not self.frame_queue:
            frame = next(self.idle)
        else:
            try:
                frame = next(self.frame_queue)
            except StopIteration:
                frame = next(self.idle)
                self.finish_action()

        # Blit settings
        blit_from_top = False
        blit_from_center = False
        blit_from_right = False
        custom_rect = False
        offset = False
        if self.action:
            if self.action[2] == "top":
                blit_from_top = True
            elif self.action[2] == "center":
                blit_from_center = True
            elif self.action[2] == "right":
                blit_from_right = True
            # Manually define horizontal offset of animation (unused)
            # if isinstance(self.action[3], int):  # Horizontal offset
            #     offset = True
            if self.action[4]:
                custom_rect = self.action[4].get_bounding_rect()
            # Call the action function with an argument (unused)
            # if self.action[5]:
            #     self.action[0](self.action[5])
            self.action[0]()

        # If there is a new frame in the animation
        if frame:
            # Save coordinates
            x = self.rect.x
            y = self.rect.y
            bot = self.rect.bottom
            center = self.rect.center
            right = self.rect.right

            self.rect = frame.get_bounding_rect()   # Changes the hitbox based on the current sprite

            if custom_rect:  # Some actions do not want to affect the hitbox
                self.rect = custom_rect

            self.rect.y = y  # Put the new rectangle in the same spot
            self.rect.x = x
            # Change the location of the rectangle depending on which spot we want to stay in place
            if blit_from_center:
                self.rect.center = center
            elif blit_from_right:
                self.rect.right = right
            elif not blit_from_top:
                # Blit from bottom
                self.rect.bottom = bot

            # if offset:
            #     blitcoord = list(frame.get_size())
            #     blitcoord[0] = self.rect.bottomright[0] - blitcoord[0]
            #     blitcoord[1] = self.rect.y

            # Index is used to know when animations have finished
            self.current_frame_index = self.frames.index(frame)
            if self.flip:  # Flip image and right align surface
                frame = pygame.transform.flip(frame, True, False)
                blitcoordinate = [self.rect.bottomright[0] - frame.get_size()[0], self.rect.bottomright[1] - frame.get_size()[1]]
                self.disp.blit(frame, blitcoordinate)
            else:
                self.disp.blit(frame, self.rect)
            self.current_frame = frame
        # If no new frame, display previous frame
        else:
            if self.flip:
                blitcoordinate = [self.rect.bottomright[0] - self.current_frame.get_size()[0], self.rect.bottomright[1] - self.current_frame.get_size()[1]]
                self.disp.blit(self.current_frame, blitcoordinate)
            else:
                self.disp.blit(self.current_frame, self.rect)

    # Clear action and frame queues
    def finish_action(self):
        self.action = None
        self.frame_queue = []

# Inherits from Character
class Ryu(Character):
    def __init__(self, flip, controller, coord, size, opponent, disp, action_provider=None):
        super().__init__(flip, controller, size, opponent, disp, action_provider=action_provider, home_x=coord[0])
        self.rect = pygame.Rect(coord, size)
        self.frames = parse_spritesheet(pygame.image.load("./ryu_spritesheet.png").convert_alpha(), [144, 130], 14, 15, size)
        self.health = TOTAL_HEALTH
        self.vel_x = 0
        self.vel_y = 0
        self.ishit = False
        self.action = None
        self.frame_queue = None
        self.input_buffer = [None]

        # Some animations are defined here instead of passing as arguments through multiple functions
        self.idle = cycle(add_delay(self.frames[10:14], 10))
        self.hit_frames = self.frames[138:141]
        self.block_frames = self.frames[44:46]

        # Keep track of special moves
        self.specials = {}
        self.special_func = []

    def reset(self):
        self.health = TOTAL_HEALTH
        self.vel_x = 0
        self.vel_y = 0
        self.ishit = False
        self.action = None
        self.frame_queue = None
        self.input_buffer = [None]
        if self.home_x is not None:
            self.rect.x = self.home_x
        elif self.flip:
            self.rect.x = 1000
        else:
            self.rect.x = 600
        self.rect.y = FLOOR - self.rect.height

    def move(self):
        super().move()

    def attack(self):
        keys = self.get_input()
        super().attack(keys,
                       mpunch_hbox=RYU_MPUNCH_HBOX, mpunch_kb=RYU_MPUNCH_KB, mpunch_st=RYU_MPUNCH_ST,
                       mpunch_frames=eval(RYU_MPUNCH), mpunch_rect=self.frames[12], mpunch_index=50,
                       mpunch_dmg=RYU_MPUNCH_DMG, mpunch_sfx=RYU_MEDIUM_SFX,
                       mkick_hbox=RYU_MKICK_HBOX, mkick_kb=RYU_MKICK_KB, mkick_st=RYU_MKICK_ST,
                       mkick_frames=eval(RYU_MKICK), mkick_rect=self.frames[12], mkick_index=63,
                       mkick_dmg=RYU_MKICK_DMG, mkick_sfx=RYU_MEDIUM_SFX,
                       hit_frame_final_index=140)

    # Extends character.hit, and plays hit sound
    def hit(self, dmg, stuntime, knockback, hit_frame_final_index):
        super().hit(dmg, stuntime, knockback, hit_frame_final_index)
        self.channel.play(RYU_HURT_SFX)






# Prototype character for chun li, sprite was too low quality
# class ChunLi(Character):
#     def __init__(self, flip, player, coord, size):
#         super().__init__(flip, player, size)
#         spritesheet = pygame.image.load("./chunli_spritesheet.png").convert_alpha()
#         self.frames = parse_spritesheet(spritesheet, [90, 138], 21, 10, [90*6, 138*6])
#         self.rect = self.frames[0].get_bounding_rect()
#         self.idle = cycle(add_delay(self.frames[:4], 9))
#     def move(self, keys):
#         super().move(keys)
