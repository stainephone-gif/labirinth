import cv2
import sys
import pygame
import pymunk
import pymunk.pygame_util
import math
import random
import time
import os
import tkinter as tk
from tkinter import filedialog

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
screen_width, screen_height = 1040, 810
screen = pygame.display.set_mode((screen_width, screen_height), pygame.NOFRAME)
pygame.display.set_caption("Game")
clock = pygame.time.Clock()
font = pygame.font.SysFont("arial", 20)

# Определение состояний игры
STATE_START_SCREEN = "start_screen"
STATE_LOAD_FINGERPRINT = "fingerprint_screen"
STATE_GAME_ACTIVE = "game_active"

# Начальное состояние игры
game_state = STATE_START_SCREEN
fingerprint_path = None

def select_fingerprint_file():
    """Открывает диалог выбора файла отпечатка."""
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(
        title="Выберите изображение отпечатка",
        filetypes=[("Изображения", "*.jpg *.jpeg *.png *.bmp")]
    )
    root.destroy()
    return file_path if file_path else None

def start_screen():
    global game_state
    screen.fill((0, 0, 0))
    start_text = font.render("Нажмите любую клавишу для загрузки отпечатка", True, (255, 255, 255))
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
            remove_index = random.randint(0, segments - 1)
            removed_indices = {remove_index, (remove_index + 1) % segments}
        else:
            remove_count = random.randint(1, 3)
            removed_indices = ensure_non_adjacent_indices(segments, remove_count)

        for j in range(segments):
            if j in removed_indices:
                continue
            angle_start = 2 * math.pi * j / segments
            angle_end = 2 * math.pi * (j + 1) / segments
            start_pos = (radius * math.cos(angle_start), radius * math.sin(angle_start))
            end_pos = (radius * math.cos(angle_end), radius * math.sin(angle_end))
            shape = pymunk.Segment(body, start_pos, end_pos, thickness)
            shape.elasticity = 0.95

            color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            shape.color = color

            space.add(shape)

        rotation_bodies.append(body)
    return rotation_bodies

def fingerprint_screen():
    global game_state, fingerprint_path
    screen.fill((0, 0, 0))
    load_text = font.render("Загрузить отпечаток", True, (0, 0, 0))
    load_button_rect = pygame.Rect(screen_width // 2 - 100, screen_height // 2 - 25, 200, 50)
    pygame.draw.rect(screen, (255, 255, 255), load_button_rect)
    load_text_rect = load_text.get_rect(center=load_button_rect.center)
    screen.blit(load_text, load_text_rect)
    pygame.display.flip()

    waiting_for_button_press = True
    while waiting_for_button_press:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if load_button_rect.collidepoint(event.pos):
                    selected = select_fingerprint_file()
                    if selected:
                        fingerprint_path = selected
                        waiting_for_button_press = False
                        game_state = STATE_GAME_ACTIVE
                        print(f"Загружен отпечаток: {fingerprint_path}")
                    else:
                        print("Файл не выбран, попробуйте снова.")

def main():
    global game_state, screen, clock, fingerprint_path

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
            crossings = analyze_fingerprint(fingerprint_path)
            if crossings < 2:
                crossings = 2

            space = pymunk.Space()
            space.gravity = (0, 900)
            add_walls(space, screen_width, screen_height)
            rotation_bodies = add_rotating_circle_barriers(space, (300, 300), 50, 25, crossings)
            ball_body, ball_shape = add_ball(space, screen_width, screen_height)

            fp_image = pygame.image.load(fingerprint_path)
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
