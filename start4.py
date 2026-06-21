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
        color_tuple = color_to_tuple(color)
        # Пропускаем почти чёрные линии (невидимые стены)
        if color_tuple[0] < 10 and color_tuple[1] < 10 and color_tuple[2] < 10:
            return
        pygame.draw.aalines(self.surface, color_tuple, False, [p1, p2])

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

# Инициализация Pygame: одно окно на основном мониторе
os.environ['SDL_VIDEO_WINDOW_POS'] = '0,0'
pygame.init()
display_info = pygame.display.Info()
screen_width, screen_height = display_info.current_w, display_info.current_h
screen = pygame.display.set_mode((screen_width, screen_height), pygame.NOFRAME)
pygame.display.set_caption("Game")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arial", 20)

# Путь к файлу отпечатка
FINGERPRINT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Fingerprint.jpg')

# Определение состояний игры
STATE_START_SCREEN = "start_screen"
STATE_LOAD_FINGERPRINT = "fingerprint_screen"
STATE_GAME_ACTIVE = "game_active"

# Время бездействия (сек), после которого игра сбрасывается на стартовый экран
IDLE_RESET_TIMEOUT = 60

# Начальное состояние игры
game_state = STATE_START_SCREEN
# Флаг: нужно ли сейчас опрашивать кнопку Save
waiting_for_scan = False

# Принудительный сброс: три одновременных нажатия Left Ctrl + Right Ctrl
_ctrl_press_count = 0
_ctrl_both_pressed = False
_ctrl_last_press_time = 0

def check_reset_shortcut():
    global _ctrl_press_count, _ctrl_both_pressed, _ctrl_last_press_time, game_state
    keys = pygame.key.get_pressed()
    both_pressed = keys[pygame.K_KP4] and keys[pygame.K_KP6]
    current_time = time.time()
    if both_pressed and not _ctrl_both_pressed:
        if current_time - _ctrl_last_press_time > 3.0:
            _ctrl_press_count = 0
        _ctrl_press_count += 1
        _ctrl_last_press_time = current_time
        if _ctrl_press_count >= 3:
            _ctrl_press_count = 0
            game_state = STATE_START_SCREEN
    _ctrl_both_pressed = both_pressed

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

def _close_confirmation_popup(demo_hwnd):
    """Закрывает всплывающее окно подтверждения (кнопка OK), если оно появилось."""
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
                    return True
        except Exception:
            pass
    return False

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
                        _close_confirmation_popup(demo_hwnd)
        except Exception:
            pass
        time.sleep(2)

def _auto_connect_sensor_loop():
    """Фоновый поток: при старте переключает формат на JPG, подключается к датчику и закрывает диалог подтверждения."""
    while True:
        try:
            demo_hwnd = win32gui.FindWindow(None, "Demo")
            if demo_hwnd:
                jpg_btn = _find_button_by_text(demo_hwnd, "JPG")
                if jpg_btn:
                    _click_button(jpg_btn)

                connect_btn = _find_button_by_text(demo_hwnd, "Connect Sensor")
                if connect_btn:
                    _click_button(connect_btn)
                    time.sleep(1)
                    _close_confirmation_popup(demo_hwnd)
                    print("Датчик подключен, формат JPG выбран.")
                    return
        except Exception:
            pass
        time.sleep(2)

def start_auto_save():
    """Запускает фоновый поток автосохранения отпечатка."""
    thread = threading.Thread(target=_auto_save_loop, daemon=True)
    thread.start()
    print("Автосохранение отпечатка запущено.")

def start_auto_connect_sensor():
    """Запускает фоновый поток подключения к датчику отпечатков при старте."""
    thread = threading.Thread(target=_auto_connect_sensor_loop, daemon=True)
    thread.start()
    print("Автоподключение датчика запущено.")

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

        check_reset_shortcut()
        if game_state == STATE_START_SCREEN:
            return False

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
    start_text = font.render("Отсканируйте свой отпечаток пальца и нажмите любую клавишу", True, (255, 255, 255))
    screen.blit(start_text, (screen_width // 2 - start_text.get_width() // 2, screen_height // 2))
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
    wait_text = font.render("Загрузка...", True, (255, 255, 255))
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

def add_static_line(space, start_pos, end_pos, thickness=5, visible=True):
    body = pymunk.Body(body_type=pymunk.Body.STATIC)
    shape = pymunk.Segment(body, start_pos, end_pos, thickness)
    shape.elasticity = 0.95
    if not visible:
        shape.shape_dynamic_color = (0, 0, 0, 255)
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
    add_static_line(space, (0, 0), (screen_width, 0), visible=False)
    add_static_line(space, (0, screen_height), (screen_width, screen_height), visible=False)
    add_static_line(space, (0, 0), (0, screen_height), visible=False)
    add_static_line(space, (screen_width, 0), (screen_width, screen_height), visible=False)

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

    start_auto_connect_sensor()
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
            num_turns = crossings * 2

            space = pymunk.Space()
            space.gravity = (0, 900)
            add_walls(space, screen_width, screen_height)
            rotation_bodies = add_spiral_barriers(space, (300, 300), 30, 25, num_turns=num_turns)
            ball_body, ball_shape = add_ball(space, screen_width, screen_height)

            fp_image = pygame.image.load(FINGERPRINT_PATH)
            fp_w, fp_h = fp_image.get_size()
            thumb_w = max(80, min(200, screen_width // 6))
            thumb_h = int(thumb_w * fp_h / fp_w)
            image = pygame.transform.smoothscale(fp_image, (thumb_w, thumb_h))

            last_action_time = time.time()

            while game_state == STATE_GAME_ACTIVE:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            game_state = STATE_START_SCREEN
                            break

                check_reset_shortcut()
                if game_state != STATE_GAME_ACTIVE:
                    break

                if ball_body.position.y + ball_shape.radius >= screen_height - 10 or \
                   ball_body.position.x < 0 or ball_body.position.x > screen_width or \
                   ball_body.position.y < 0 or ball_body.position.y > screen_height:
                    game_state = STATE_START_SCREEN
                    break

                keys = pygame.key.get_pressed()
                if keys[pygame.K_KP4]:
                    for body in rotation_bodies:
                        body.angle -= 0.05
                    last_action_time = time.time()
                if keys[pygame.K_KP6]:
                    for body in rotation_bodies:
                        body.angle += 0.05
                    last_action_time = time.time()

                if time.time() - last_action_time > IDLE_RESET_TIMEOUT:
                    game_state = STATE_START_SCREEN
                    break

                space.step(1/50.0)
                screen.fill((0, 0, 0))
                space.debug_draw(draw_options)
                pygame.draw.circle(screen, (255, 0, 0), (int(ball_body.position.x), int(ball_body.position.y)), ball_shape.radius)
                iw, ih = image.get_size()
                screen.blit(image, (screen_width - iw - 10, screen_height - ih - 10))

                pygame.display.flip()
                clock.tick(60)

if __name__ == "__main__":
    main()
