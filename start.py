import cv2
import sys
import pygame
import pymunk
import pymunk.pygame_util
import math
import random
import time
import os

def color_to_tuple(color):
    """Преобразует объект цвета в кортеж (R, G, B) или (R, G, B, A)."""
    # Предположим, что объект цвета имеет атрибуты r, g, b (и возможно a)
    if hasattr(color, 'a'):  # Проверка наличия альфа-канала
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
            if len(color) == 3:  # Проверяем, есть ли у нас только RGB, без альфа-канала
                return color + (255,)  # Дополняем недостающий альфа-канал
            elif len(color) != 4:  # Если длина не равна 3 (RGB) или 4 (RGBA), возбуждаем ошибку
                raise ValueError("Неверный формат цвета: ожидается RGB или RGBA")
            return color  # Возвращаем цвет, если формат правильный
        else:
            # Если у фигуры нет кастомного цвета, возвращаем стандартный цвет
            # Обязательно включаем альфа-канал
            return (255, 255, 255, 0)  # Белый цвет с полной непрозрачностью

# Инициализация Pygame
pygame.init()
screen_width, screen_height = 1040, 810
screen = pygame.display.set_mode((screen_width, screen_height))
pygame.display.set_caption("Game")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arial", 20)

# Определение состояний игры
STATE_START_SCREEN = "start_screen"
STATE_LOAD_FINGERPRINT = "fingerprint_screen"
STATE_GAME_ACTIVE = "game_active"

# Начальное состояние игры
game_state = STATE_START_SCREEN

def start_screen():
    global game_state
    screen.fill((0, 0, 0))
    start_text = font.render("Отсканируйте отпечаток пальца для начала и нажмите любую клавишу", True, (255, 255, 255))
    screen.blit(start_text, (screen_width // 2 - start_text.get_width() // 2, screen_height // 2 - start_text.get_height() // 2))
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

def wait_for_fingerprint(filepath='Fingerprint.jpg', timeout=60):
    """Ждёт появления или обновления файла отпечатка. Возвращает True если файл обновился."""
    # Запоминаем время модификации файла (если он уже существует)
    old_mtime = None
    if os.path.exists(filepath):
        old_mtime = os.path.getmtime(filepath)

    start_time = time.time()
    while time.time() - start_time < timeout:
        # Обрабатываем события pygame чтобы окно не зависало
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

        if os.path.exists(filepath):
            current_mtime = os.path.getmtime(filepath)
            if old_mtime is None or current_mtime > old_mtime:
                time.sleep(0.2)  # Даём файлу дозаписаться
                print("Отпечаток получен.")
                return True

        time.sleep(0.1)

    print("Таймаут: отпечаток не получен.")
    return False

def count_line_crossings(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        print("Ошибка: изображение не найдено.")
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
            
def add_static_line(space, start_pos, end_pos, thickness=5):
    body = pymunk.Body(body_type=pymunk.Body.STATIC)
    shape = pymunk.Segment(body, start_pos, end_pos, thickness)
    shape.elasticity = 0.95
    space.add(body, shape)

def add_ball(space, screen_width, screen_height, radius=6):
    mass = 1
    moment = pymunk.moment_for_circle(mass, 0, radius)
    body = pymunk.Body(mass, moment)
    body.position = (screen_width / 3, screen_height / 2)  # Центр экрана
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
    """Создаёт лабиринт в виде спирали Архимеда с прорезями.

    center — центр спирали
    start_radius — начальный радиус
    spacing — расстояние между витками
    num_turns — количество витков спирали
    segments_per_turn — сегментов на один виток
    gap_count — количество прорезей на каждый виток
    """
    center_x = screen_width // 3
    center_y = screen_height // 2
    center = (center_x, center_y)

    body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
    body.position = center
    space.add(body)

    total_segments = num_turns * segments_per_turn

    # Генерируем прорези: gap_count штук на каждый виток, не соседние
    gap_indices = set()
    for turn in range(num_turns):
        turn_start = turn * segments_per_turn
        gaps_this_turn = random.randint(max(1, gap_count - 1), gap_count + 1)
        placed = 0
        attempts = 0
        while placed < gaps_this_turn and attempts < 200:
            idx = turn_start + random.randint(0, segments_per_turn - 1)
            # Проверяем что ни сам индекс, ни соседи не заняты
            if idx not in gap_indices and (idx - 1) not in gap_indices and (idx + 1) not in gap_indices:
                # Убираем 2 соседних сегмента для ширины прохода
                gap_indices.add(idx)
                gap_indices.add(idx + 1)
                placed += 1
            attempts += 1

    # Коэффициент роста радиуса: b = spacing / (2*pi)
    b = spacing / (2 * math.pi)

    for seg in range(total_segments):
        if seg in gap_indices:
            continue

        # Угол начала и конца сегмента
        theta_start = 2 * math.pi * seg / segments_per_turn
        theta_end = 2 * math.pi * (seg + 1) / segments_per_turn

        # Радиус в каждой точке по формуле Архимеда: r = a + b*θ
        r_start = start_radius + b * theta_start
        r_end = start_radius + b * theta_end

        start_pos = (r_start * math.cos(theta_start), r_start * math.sin(theta_start))
        end_pos = (r_end * math.cos(theta_end), r_end * math.sin(theta_end))

        shape = pymunk.Segment(body, start_pos, end_pos, thickness)
        shape.elasticity = 0.95

        shape.color = (255, 255, 255)

        space.add(shape)

    return [body]
    
def fingerprint_screen():
    global game_state
    screen.fill((0, 0, 0))
    wait_text = font.render("Приложите палец к сканеру...", True, (255, 255, 255))
    screen.blit(wait_text, (screen_width // 2 - wait_text.get_width() // 2, screen_height // 2 - wait_text.get_height() // 2))
    pygame.display.flip()

    if wait_for_fingerprint():
        game_state = STATE_GAME_ACTIVE
    else:
        game_state = STATE_START_SCREEN
    
def main():
    global game_state, screen, clock
    
    draw_options = CustomDrawOptions(screen)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if game_state == STATE_START_SCREEN and event.type == pygame.KEYDOWN:
                game_state = STATE_LOAD_FINGERPRINT
            elif game_state == STATE_LOAD_FINGERPRINT and event.type == pygame.MOUSEBUTTONDOWN:
                # Здесь можно добавить дополнительные условия, например, проверку позиции мыши для определения нажатия на кнопку
                game_state = STATE_GAME_ACTIVE
            elif game_state == STATE_GAME_ACTIVE and event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    game_state = STATE_START_SCREEN

        if game_state == STATE_START_SCREEN:
            start_screen()

        elif game_state == STATE_LOAD_FINGERPRINT:
            fingerprint_screen()
            
        elif game_state == STATE_GAME_ACTIVE:
            screen.fill((0, 0, 0))
            crossings = analyze_fingerprint('Fingerprint.jpg')
            if crossings < 2:
                crossings = 2

            space = pymunk.Space()
            space.gravity = (0, 900)
            add_walls(space, screen_width, screen_height)
            rotation_bodies = add_spiral_barriers(space, (300, 300), 30, 25, num_turns=crossings)
            ball_body, ball_shape = add_ball(space, screen_width, screen_height)

            # Загружаем изображение отпечатка для отображения в углу
            fp_image = pygame.image.load('Fingerprint.jpg')
            image = pygame.transform.scale(fp_image, (350, 200))
            
            # Игровой цикл
            while game_state == STATE_GAME_ACTIVE:  # Используем условие для выхода из цикла при смене состояния
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    if event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_BACKSPACE:
                            game_state = STATE_START_SCREEN  # Возврат к стартовому экрану
                            break  # Выход из внутреннего цикла

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