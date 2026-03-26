import cv2
import numpy as np
import sys
import pygame
import pymunk
import pymunk.pygame_util
import math
import random
import time
import os
import threading
import win32gui
import win32con

def color_to_tuple(color):
    if hasattr(color, 'a'):
        return (color.r, color.g, color.b, color.a)
    else:
        return (color.r, color.g, color.b)


class CustomDrawOptions(pymunk.pygame_util.DrawOptions):
    def __init__(self, surface):
        super().__init__(surface)

    def draw_segment(self, p1, p2, color):
        pygame.draw.aalines(self.surface, color_to_tuple(color), False, [p1, p2])

    def color_for_shape(self, shape):
        if hasattr(shape, 'shape_dynamic_color'):
            color = shape.shape_dynamic_color
            if len(color) == 3:
                return color + (255,)
            elif len(color) != 4:
                raise ValueError("Неверный формат цвета: ожидается RGB или RGBA")
            return color
        else:
            return (255, 255, 255, 0)

# Устанавливаем позицию окна перед инициализацией Pygame
os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"

# Инициализация Pygame
pygame.init()
display_info = pygame.display.Info()
screen_width, screen_height = display_info.current_w, display_info.current_h
screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
pygame.display.set_caption("Game")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arial", 20)

# Путь к файлу отпечатка
FINGERPRINT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Fingerprint.jpg')

# Определение состояний игры
STATE_START_SCREEN = "start_screen"
STATE_LOAD_FINGERPRINT = "fingerprint_screen"
STATE_GAME_ACTIVE = "game_active"

# Начальное состояние игры
game_state = STATE_START_SCREEN
# Флаг: нужно ли сейчас опрашивать кнопку Save
waiting_for_scan = False

# --- Автосохранение отпечатка через win32gui ---

def _find_all_children(parent_hwnd):
    """Рекурсивно собирает все дочерние окна (включая вложенные в панели)."""
    children = []
    def callback(hwnd, _):
        children.append(hwnd)
        return True
    try:
        win32gui.EnumChildWindows(parent_hwnd, callback, None)
    except Exception:
        pass
    return children

def _find_button_by_text(parent_hwnd, target_text):
    """Ищет кнопку по тексту среди всех дочерних окон."""
    for hwnd in _find_all_children(parent_hwnd):
        try:
            text = win32gui.GetWindowText(hwnd)
            if target_text.lower() in text.lower():
                return hwnd
        except Exception:
            pass
    return None

def _click_button(hwnd):
    """Отправляет нажатие кнопки несколькими способами для совместимости с Delphi."""
    win32gui.PostMessage(hwnd, win32con.BM_CLICK, 0, 0)
    ctrl_id = win32gui.GetDlgCtrlID(hwnd)
    parent = win32gui.GetParent(hwnd)
    while win32gui.GetParent(parent):
        parent = win32gui.GetParent(parent)
    win32gui.PostMessage(parent, win32con.WM_COMMAND, ctrl_id, hwnd)

def _auto_save_loop():
    """Фоновый поток: нажимает Save Image в Demo.exe только когда игра ждёт отпечаток."""
    while True:
        try:
            if waiting_for_scan:
                demo_hwnd = win32gui.FindWindow(None, "Demo")
                if demo_hwnd:
                    save_btn = _find_button_by_text(demo_hwnd, "Save Image")
                    if save_btn:
                        _click_button(save_btn)
                        time.sleep(0.5)
                        # Закрываем диалог подтверждения
                        all_windows = []
                        def enum_callback(hwnd, results):
                            results.append(hwnd)
                            return True
                        win32gui.EnumWindows(enum_callback, all_windows)
                        for hwnd in all_windows:
                            try:
                                title = win32gui.GetWindowText(hwnd)
                                if title in ["Information", "Информация", "Confirm", "Demo"] and hwnd != demo_hwnd:
                                    ok_btn = _find_button_by_text(hwnd, "OK")
                                    if ok_btn:
                                        _click_button(ok_btn)
                                        break
                            except Exception:
                                pass
        except Exception:
            pass
        time.sleep(2)

def start_auto_save():
    """Запускает фоновый поток автосохранения отпечатка."""
    thread = threading.Thread(target=_auto_save_loop, daemon=True)
    thread.start()
    print("Автосохранение отпечатка запущено.")

# --- Ожидание отпечатка ---

def wait_for_fingerprint(timeout=120):
    """Ждёт появления или обновления файла отпечатка."""
    old_mtime = None
    if os.path.exists(FINGERPRINT_PATH):
        old_mtime = os.path.getmtime(FINGERPRINT_PATH)

    start_time = time.time()
    while time.time() - start_time < timeout:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        if os.path.exists(FINGERPRINT_PATH) and os.path.getsize(FINGERPRINT_PATH) > 0:
            current_mtime = os.path.getmtime(FINGERPRINT_PATH)
            if old_mtime is None or current_mtime > old_mtime:
                time.sleep(0.5)
                if os.path.getsize(FINGERPRINT_PATH) > 0:
                    print("Отпечаток получен.")
                    return True

        time.sleep(0.1)

    print("Таймаут: отпечаток не получен.")
    return False

# --- Экраны ---

def start_screen():
    global game_state
    screen.fill((0, 0, 0))
    start_text = font.render("Запустите Demo.exe, нажмите Init, затем любую клавишу здесь", True, (255, 255, 255))
    hint_text = font.render("Отпечаток сохранится автоматически при сканировании", True, (150, 150, 150))
    screen.blit(start_text, (screen_width // 2 - start_text.get_width() // 2, screen_height // 2 - 30))
    screen.blit(hint_text, (screen_width // 2 - hint_text.get_width() // 2, screen_height // 2 + 10))
    pygame.display.flip()

    waiting_for_keypress = True
    while waiting_for_keypress:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                waiting_for_keypress = False
                game_state = STATE_LOAD_FINGERPRINT

def fingerprint_screen():
    global game_state, waiting_for_scan
    screen.fill((0, 0, 0))
    wait_text = font.render("Приложите палец к сканеру...", True, (255, 255, 255))
    screen.blit(wait_text, (screen_width // 2 - wait_text.get_width() // 2, screen_height // 2 - wait_text.get_height() // 2))
    pygame.display.flip()

    waiting_for_scan = True
    if wait_for_fingerprint():
        waiting_for_scan = False
        game_state = STATE_GAME_ACTIVE
    else:
        waiting_for_scan = False
        game_state = STATE_START_SCREEN

# --- Анализ отпечатка ---

def count_line_crossings(image_path):
    if not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
        print("Ошибка: файл отпечатка пуст или не найден.")
        return 0
    data = np.fromfile(image_path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        print("Ошибка: не удалось декодировать изображение.")
        return 0

    _, binary_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
    height, width = binary_img.shape
    middle_y = height // 2

    crossings = 0
    was_black = binary_img[middle_y, 0] < 127

    for x in range(1, width):
        is_black = binary_img[middle_y, x] < 127
        if is_black != was_black:
            crossings += 1
            was_black = is_black

    return crossings // 6

def analyze_fingerprint(image_path):
    crossings = count_line_crossings(image_path)
    print(f"Линия пересекает черные области {crossings} раз(а).")
    return crossings

# --- Физика лабиринта ---

def add_static_line(space, start_pos, end_pos, thickness=5):
    body = pymunk.Body(body_type=pymunk.Body.STATIC)
    shape = pymunk.Segment(body, start_pos, end_pos, thickness)
    shape.elasticity = 0.95
    space.add(body, shape)

def add_ball(space, screen_width, screen_height, radius=6):
    mass = 1
    moment = pymunk.moment_for_circle(mass, 0, radius)
    body = pymunk.Body(mass, moment)
    body.position = (screen_width / 3, screen_height / 2)
    shape = pymunk.Circle(body, radius)
    shape.elasticity = 0.95
    space.add(body, shape)
    return body, shape

def add_walls(space, screen_width, screen_height):
    add_static_line(space, (0, 0), (screen_width, 0))
    add_static_line(space, (0, screen_height), (screen_width, screen_height))
    add_static_line(space, (0, 0), (0, screen_height))
    add_static_line(space, (screen_width, 0), (screen_width, screen_height))

def add_spiral_barriers(space, center, start_radius, spacing, num_turns, segments_per_turn=30, gap_count=3, thickness=2):
    """Создаёт лабиринт в виде спирали Архимеда с прорезями."""
    center_x = screen_width // 3
    center_y = screen_height // 2
    center = (center_x, center_y)

    body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
    body.position = center
    space.add(body)

    total_segments = num_turns * segments_per_turn

    gap_indices = set()
    for turn in range(num_turns):
        turn_start = turn * segments_per_turn
        gaps_this_turn = random.randint(max(1, gap_count - 1), gap_count + 1)
        placed = 0
        attempts = 0
        while placed < gaps_this_turn and attempts < 200:
            idx = turn_start + random.randint(0, segments_per_turn - 1)
            if idx not in gap_indices and (idx - 1) not in gap_indices and (idx + 1) not in gap_indices:
                gap_indices.add(idx)
                gap_indices.add(idx + 1)
                placed += 1
            attempts += 1

    b = spacing / (2 * math.pi)

    for seg in range(total_segments):
        if seg in gap_indices:
            continue

        theta_start = 2 * math.pi * seg / segments_per_turn
        theta_end = 2 * math.pi * (seg + 1) / segments_per_turn

        r_start = start_radius + b * theta_start
        r_end = start_radius + b * theta_end

        start_pos = (r_start * math.cos(theta_start), r_start * math.sin(theta_start))
        end_pos = (r_end * math.cos(theta_end), r_end * math.sin(theta_end))

        shape = pymunk.Segment(body, start_pos, end_pos, thickness)
        shape.elasticity = 0.95
        shape.color = (255, 255, 255)

        space.add(shape)

    return [body]

# --- Главный цикл ---

def main():
    global game_state, screen, clock

    start_auto_save()

    draw_options = CustomDrawOptions(screen)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        if game_state == STATE_START_SCREEN:
            start_screen()

        elif game_state == STATE_LOAD_FINGERPRINT:
            fingerprint_screen()

        elif game_state == STATE_GAME_ACTIVE:
            screen.fill((0, 0, 0))
            crossings = analyze_fingerprint(FINGERPRINT_PATH)
            if crossings < 2:
                crossings = 2
            num_turns = crossings * 3

            space = pymunk.Space()
            space.gravity = (0, 900)
            add_walls(space, screen_width, screen_height)
            rotation_bodies = add_spiral_barriers(space, (300, 300), 30, 25, num_turns=num_turns)
            ball_body, ball_shape = add_ball(space, screen_width, screen_height)

            fp_image = pygame.image.load(FINGERPRINT_PATH)
            image = pygame.transform.scale(fp_image, (350, 200))

            while game_state == STATE_GAME_ACTIVE:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            game_state = STATE_START_SCREEN
                            break

                if game_state != STATE_GAME_ACTIVE:
                    break

                if ball_body.position.y + ball_shape.radius >= screen_height:
                    game_state = STATE_START_SCREEN
                    break

                keys = pygame.key.get_pressed()
                if keys[pygame.K_KP4]:
                    for body in rotation_bodies:
                        body.angle -= 0.05
                if keys[pygame.K_KP6]:
                    for body in rotation_bodies:
                        body.angle += 0.05

                space.step(1/50.0)
                screen.fill((0, 0, 0))
                space.debug_draw(draw_options)
                pygame.draw.circle(screen, (255, 0, 0), (int(ball_body.position.x), int(ball_body.position.y)), ball_shape.radius)
                screen.blit(image, (650, 550))

                pygame.display.flip()
                clock.tick(60)

if __name__ == "__main__":
    main()
