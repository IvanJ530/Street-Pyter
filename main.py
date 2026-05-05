# Street Fighter Pygame Clone
# Version 1.0.0
# Created for itch.io
# Charles Huang 6/17/2022
# Keyboard Controls -- WASD for movement UIOJKL for attack
# Controller controls -- left stick for movement, abxy + bumpers for attack
# Special move -- Hadouken -- Down, Down-Forward, Forward + Punch
import pygame
from pygame.locals import *
from time import sleep
import random
import os
import sys
import time

import numpy as np

# Make the top-level project root (which holds the `motion/` package) importable
# regardless of whether the game is launched from its own directory or the repo
# root. This is only consumed when GESTRA_WEBCAM=1; without that flag the rest
# of the import block behaves exactly as before.
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib import *
from settings import *

# Initialize pygame
pygame.init()
pygame.display.set_caption("Street Fighter Pygame Clone v1.0.0")

# Auto-detect screen size and scale the game to fit
_screen_info = pygame.display.Info()
_native_w, _native_h = _screen_info.current_w, _screen_info.current_h
# Leave some room for the title bar / dock (~80px)
_max_w = _native_w - 40
_max_h = _native_h - 100
_scale = min(_max_w / 1920, _max_h / 1080)
ACTUAL_W = int(1920 * _scale)
ACTUAL_H = int(1080 * _scale)

# Internal render surface stays at 1920x1080 so all game logic is unchanged.
# We scale-blit it onto the actual window each frame.
_internal_surf = pygame.Surface((1920, 1080))
disp = _internal_surf
_window = pygame.display.set_mode((ACTUAL_W, ACTUAL_H))
print(f"Screen: {_native_w}x{_native_h}, game window: {ACTUAL_W}x{ACTUAL_H} (scale {_scale:.2f})")

clock = pygame.time.Clock()

# Game states
MENU = 0
GAME = 1
GAME_OVER = 2
current_state = MENU

# Font setup
font = pygame.font.Font(None, 74)
small_font = pygame.font.Font(None, 36)

def draw_menu():
    disp.fill((0, 0, 0))
    title = font.render("GESTRA", True, (255, 80, 80))
    subtitle = small_font.render("Motion-Controlled Street Fighter", True, (200, 200, 200))
    start_text = small_font.render("Press SPACE to Start", True, (255, 255, 255))

    _is_webcam = os.environ.get("GESTRA_WEBCAM") == "1"
    if _is_webcam:
        p1_line = small_font.render("Player 1: YOUR BODY (webcam)", True, (100, 255, 100))
        p1_detail = small_font.render("Raise Arm = Punch / Lean = Move / Still = Block", True, (180, 180, 180))
    else:
        p1_line = small_font.render("Player 1: WASD + UIOJKL", True, (255, 255, 255))
        p1_detail = None
    p2_line = small_font.render("Player 2: AI Opponent", True, (255, 150, 150))
    esc_line = small_font.render("ESC = Menu / Quit", True, (140, 140, 140))

    cx = SCREEN_WIDTH // 2
    disp.blit(title, (cx - title.get_width() // 2, 200))
    disp.blit(subtitle, (cx - subtitle.get_width() // 2, 280))
    disp.blit(start_text, (cx - start_text.get_width() // 2, 400))
    disp.blit(p1_line, (cx - p1_line.get_width() // 2, 520))
    if p1_detail:
        disp.blit(p1_detail, (cx - p1_detail.get_width() // 2, 560))
    disp.blit(p2_line, (cx - p2_line.get_width() // 2, 620))
    disp.blit(esc_line, (cx - esc_line.get_width() // 2, 720))

def draw_game_over(winner):
    disp.fill((0, 0, 0))
    cx = SCREEN_WIDTH // 2
    game_over = font.render(f"PLAYER {winner} WINS!", True, (255, 80, 80))
    restart_text = small_font.render("ANY KEY = Rematch    ESC = Menu", True, (200, 200, 200))
    disp.blit(game_over, (cx - game_over.get_width() // 2, 400))
    disp.blit(restart_text, (cx - restart_text.get_width() // 2, 500))

playersize = [144*5, 130*5]
#playersize = [144, 130] #  small

# Load all music into a list
music = []
try:
    if not os.path.exists("./music"):
        os.makedirs("./music")
    for filename in os.listdir("./music"):
        if filename.endswith(".mp3"):
            music.append("./music/" + filename)
except Exception as e:
    print(f"Warning: Could not load music directory: {e}")

# Start up music
pygame.mixer.set_num_channels(2)
if music:
    try:
        pygame.mixer.music.load(random.choice(music))
        pygame.mixer.music.set_volume(0.5)
        pygame.mixer.music.play()
        pygame.mixer.music.set_endevent(MIDIIN)
    except Exception as e:
        print(f"Warning: Could not play music: {e}")

# Game is designed for keyboard + controller. Without controller both characters will be mirrors of each other
try:
    controller = pygame.joystick.Joystick(0)
    controller.init()
    print("Controller found, using controller for Player 2")
    use_controller = True
except:
    print("No controller found, using keyboard for both players")
    controller = None
    use_controller = False

# Load background
try:
    background = pygame.transform.scale(pygame.image.load("./stage.png").convert_alpha(), (1920, 1080))
except Exception as e:
    print(f"Warning: Could not load background: {e}")
    background = pygame.Surface((1920, 1080))
    background.fill((0, 0, 0))

# Optional Gestra hooks for Player 1: webcam motion control or a deterministic
# stub provider for smoke-testing the integration without a webcam or ML model.
# Both default off so launching with no env vars keeps the original keyboard
# behavior intact.
p1_action_provider = None
_pose_predictor = None
if os.environ.get("GESTRA_STUB_ACTION") == "1":
    from motion.stub_action import make_stub_provider
    p1_action_provider = make_stub_provider()
    print("Gestra: stub action provider active for Player 1 (no webcam, no ML)")
elif os.environ.get("GESTRA_WEBCAM") == "1":
    from motion.calibration import run_calibration
    print("Gestra: starting camera calibration...")
    run_calibration()

    # Quick-record: let the user record ~30s of their own movements
    from motion.quick_record import run_quick_record
    new_data_dir = run_quick_record()
    if new_data_dir:
        from motion.quick_train import quick_train
        import threading
        print("Gestra: training on your data...")

        train_done = threading.Event()
        def _train():
            quick_train(newest_dir=new_data_dir)
            train_done.set()
        threading.Thread(target=_train, daemon=True).start()

        # Show training progress screen while model trains
        import cv2
        train_start = time.time()
        while not train_done.is_set():
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            elapsed = int(time.time() - train_start)
            cv2.putText(img, "Training your model...", (120, 180),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
            cv2.putText(img, f"Please wait (~20-40 seconds)", (130, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1)
            cv2.putText(img, f"Elapsed: {elapsed}s", (240, 300),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
            dots = "." * ((elapsed % 3) + 1)
            cv2.putText(img, dots, (320, 350),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 2)
            cv2.imshow("Gestra - Quick Record", img)
            cv2.waitKey(100)
        cv2.destroyAllWindows()
    else:
        print("Gestra: skipped quick recording")

    # Auto-detect: use personal model if it exists, otherwise fall back to rules
    _personal_model = os.path.join(_PROJECT_ROOT, "motion", "models", "action_personal.pt")
    if os.path.exists(_personal_model) and os.environ.get("GESTRA_RULES_ONLY") != "1":
        from motion.personal_detector import PersonalModelDetector
        _pose_predictor = PersonalModelDetector()
        print("Gestra: personal ML model active for Player 1")
    else:
        from motion.upper_body_detector import UpperBodyDetector
        _pose_predictor = UpperBodyDetector()
        print("Gestra: rule-based detector active for Player 1")
    _pose_predictor.start()
    p1_action_provider = _pose_predictor.latest_action

# Initialize players
player1 = Ryu(False, None, [600, FLOOR], playersize, None, disp, action_provider=p1_action_provider)
player1.player = 0  # Set player number for key binding
# Player 2 is always AI
from motion.ai_opponent import make_ai_provider
p2_ai = make_ai_provider()
player2 = Ryu(True, None, [1000, FLOOR], playersize, player1, disp, action_provider=p2_ai)
player2.player = 1
player1.opponent = player2

# Game loop
running = True
while running:
    events = pygame.event.get()
    for event in events:
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if current_state == GAME_OVER:
                    current_state = MENU
                elif current_state == GAME:
                    current_state = MENU
                else:
                    running = False
            if event.key == pygame.K_SPACE and current_state == MENU:
                current_state = GAME
                player1.reset()
                player2.reset()
            if current_state == GAME_OVER and event.key != pygame.K_ESCAPE:
                current_state = GAME
                player1.reset()
                player2.reset()
        # Randomly pick a new song once the current one finishes
        if event.type == pygame.MIDIIN and music:
            try:
                pygame.mixer.music.load(random.choice(music))
                pygame.mixer.music.set_volume(0.5)
                pygame.mixer.music.play()
                pygame.mixer.music.set_endevent(MIDIIN)
            except Exception as e:
                print(f"Warning: Could not play next song: {e}")

    if current_state == MENU:
        draw_menu()
    elif current_state == GAME:
        disp.blit(background, (0,0))
        player1.attack()
        player2.attack()
        player1.update()
        player2.update()
        player1.move()
        player2.move()
        draw_hpbar(disp, player1, player2)
        
        # Check for game over
        if player1.health <= 0 or player2.health <= 0:
            current_state = GAME_OVER
            winner = 2 if player1.health <= 0 else 1
    elif current_state == GAME_OVER:
        draw_game_over(winner)

    pygame.transform.scale(_internal_surf, (ACTUAL_W, ACTUAL_H), _window)
    pygame.display.flip()
    clock.tick(60)

if _pose_predictor is not None:
    _pose_predictor.stop()

pygame.quit()
sys.exit()


