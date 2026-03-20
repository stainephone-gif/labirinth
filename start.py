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
    img = cv2.imread('Fingerprint.jpg', cv2.IMREAD_GRAYSCALE)
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

def ensure_non_adjacent_indices(total_segments, remove_count):
    removed_indices = set()
    while len(removed_indices) < remove_count:
        index = random.randint(0, total_segments - 1)
        if index not in removed_indices and (index - 1) % total_segments not in removed_indices and (index + 1) % total_segments not in removed_indices:
            removed_indices.add(index)
    return list(removed_indices)

def add_rotating_circle_barriers(space, center, start_radius, radius_step, number_of_circles, segments=30, thickness=2):
    center_x = screen_width // 3
    center_y = screen_height // 2
    center = (center_x, center_y)
    
    rotation_bodies = []
    for i in range(number_of_circles):
        radius = start_radius + i * radius_step
        body = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        body.position = center
        space.add(body)

        if i == 0:
            # Для первой окружности определяем индекс для удаления двух соседних сегментов
            remove_index = random.randint(0, segments - 1)
            removed_indices = {remove_index, (remove_index + 1) % segments}
        else:
            # У остальных окружностей удаляем от 1 до 3 случайных сегментов
            remove_count = random.randint(1, 3)
            removed_indices = ensure_non_adjacent_indices(segments, remove_count)

        for i in range(segments):
            if i in removed_indices:
                continue
            angle_start = 2 * math.pi * i / segments
            angle_end = 2 * math.pi * (i + 1) / segments
            start_pos = (radius * math.cos(angle_start), radius * math.sin(angle_start))
            end_pos = (radius * math.cos(angle_end), radius * math.sin(angle_end))
            shape = pymunk.Segment(body, start_pos, end_pos, thickness)
            shape.elasticity = 0.95
            
            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            shape.color = color
            
            space.add(shape)

        rotation_bodies.append(body)
    return rotation_bodies
    
def draw_button(screen, text, position, size, action=None):
    font = pygame.font.SysFont("arial", 20)
    text_render = font.render(text, True, (255, 255, 255))
    button_rect = pygame.Rect(position[0], position[1], size[0], size[1])
    pygame.draw.rect(screen, (0, 0, 255), button_rect)
    text_rect = text_render.get_rect(center=button_rect.center)
    screen.blit(text_render, text_rect)
    
    # Проверка нажатия кнопки
    mouse_pos = pygame.mouse.get_pos()
    click = pygame.mouse.get_pressed()
    if button_rect.collidepoint(mouse_pos) and click[0] == 1 and action:
        action()
        
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
            game_active = True  # Активируем игру
            screen.fill((0, 0, 0))
            # После активации игры пользователем
            # Анализ изображения и получение количества пересечений линий
            crossings = analyze_fingerprint('Fingerprint.jpg')

            space = pymunk.Space()
            space.gravity = (0, 900)
            add_walls(space, screen_width, screen_height)
            rotation_bodies = add_rotating_circle_barriers(space, (300, 300), 50, 25, crossings)
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
                    break  # Если состояние изменилось, выходим из игрового цикла

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