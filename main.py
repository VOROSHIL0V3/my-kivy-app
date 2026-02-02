# main.py
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.graphics import Color, Line, Ellipse, InstructionGroup
from kivy.graphics.context_instructions import Rotate, PushMatrix, PopMatrix
from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
import math
import json
import os
from datetime import datetime

class GeometryVisualizerKivy(App):
    def build(self):
        # Основной контейнер
        self.root = BoxLayout(orientation='vertical')

        # 1. Верхняя панель информации
        self.info_label = Label(
            text='[size=18][b]Геометрический визуализатор[/b][/size]\nКоснитесь экрана для добавления вершин',
            size_hint=(1, 0.15),
            markup=True,
            halign='center',
            valign='middle'
        )
        self.info_label.bind(size=self.info_label.setter('text_size'))
        self.root.add_widget(self.info_label)

        # 2. Центральный холст для рисования
        from kivy.uix.widget import Widget
        self.canvas_widget = Widget()
        self.canvas_widget.bind(on_touch_down=self.on_touch_down)
        self.canvas_widget.bind(on_touch_move=self.on_touch_move)
        self.root.add_widget(self.canvas_widget)

        # 3. Нижняя панель кнопок
        button_panel = BoxLayout(size_hint=(1, 0.12))

        buttons = [
            ('Сброс', self.reset_app),
            ('Отмена', self.undo_action),
            ('Углы', self.toggle_angles),
            ('Стороны', self.toggle_sides),
            ('Сетка', self.toggle_grid),
            ('Пример', self.load_example),
        ]

        for text, callback in buttons:
            btn = Button(text=text, size_hint=(0.16, 1))
            btn.bind(on_press=callback)
            button_panel.add_widget(btn)

        self.root.add_widget(button_panel)

        # Инициализация данных
        self.vertices = []
        self.history = []
        self.show_angles = True
        self.show_sides = True
        self.show_grid = False
        self.selected_vertex = None
        self.dragging = False
        self.angle_mode = "internal"

        # Цвета
        self.colors = {
            'bg': (0.1, 0.1, 0.18, 1),
            'grid': (0.23, 0.23, 0.36, 1),
            'vertex': (0.3, 0.79, 0.94, 1),     # Голубой
            'vertex_selected': (0.97, 0.15, 0.52, 1),  # Розовый
            'edge': (1, 1, 1, 1),               # Белый
            'angle': [
                (1, 0.35, 0.37, 1),    # Красный
                (0.35, 0.79, 0.15, 1), # Зеленый
                (0.2, 0.63, 0.77, 1),  # Синий
                (0.95, 0.61, 0.07, 1), # Желтый
                (0.42, 0.3, 0.58, 1)   # Фиолетовый
            ]
        }

        # Фон холста
        self.canvas_widget.canvas.before.clear()
        with self.canvas_widget.canvas.before:
            Color(*self.colors['bg'])
            self.bg_rect = InstructionGroup()

        # Начальная отрисовка
        self.redraw_canvas()

        return self.root

    # ==================== МАТЕМАТИЧЕСКИЕ ФУНКЦИИ ====================
    def calculate_angle(self, A, B, C, mode="internal"):
        """Вычисляет угол ABC в градусах"""
        BA = (A[0] - B[0], A[1] - B[1])
        BC = (C[0] - B[0], C[1] - B[1])

        dot_product = BA[0] * BC[0] + BA[1] * BC[1]
        len_BA = math.sqrt(BA[0]**2 + BA[1]**2)
        len_BC = math.sqrt(BC[0]**2 + BC[1]**2)

        if len_BA * len_BC == 0:
            return 0

        cos_angle = max(-1, min(1, dot_product / (len_BA * len_BC)))
        angle = math.degrees(math.acos(cos_angle))

        # Определяем направление
        cross_product = BA[0] * BC[1] - BA[1] * BC[0]
        if cross_product < 0:
            angle = 360 - angle

        return angle if mode == "internal" else 360 - angle

    def calculate_side_lengths(self):
        """Вычисляет длины всех сторон"""
        if len(self.vertices) < 2:
            return []

        lengths = []
        for i in range(len(self.vertices)):
            j = (i + 1) % len(self.vertices)
            dx = self.vertices[j][0] - self.vertices[i][0]
            dy = self.vertices[j][1] - self.vertices[i][1]
            lengths.append(math.sqrt(dx*dx + dy*dy))

        return lengths

    def get_polygon_type(self):
        """Определяет тип многоугольника"""
        n = len(self.vertices)
        if n < 3:
            return "Не замкнуто"

        types = {
            3: "Треугольник", 4: "Четырёхугольник",
            5: "Пятиугольник", 6: "Шестиугольник",
            7: "Семиугольник", 8: "Восьмиугольник"
        }

        type_name = types.get(n, f"{n}-угольник")

        if n == 3:
            angles = []
            for i in range(n):
                A = self.vertices[(i-1) % n]
                B = self.vertices[i]
                C = self.vertices[(i+1) % n]
                angles.append(self.calculate_angle(A, B, C))

            if all(abs(a - 60) < 5 for a in angles):
                type_name += " (равносторонний)"

        return type_name

    def save_state(self):
        """Сохраняет текущее состояние в историю"""
        self.history.append(self.vertices.copy())
        if len(self.history) > 20:
            self.history.pop(0)

    def undo_action(self, instance=None):
        """Отменяет последнее действие"""
        if len(self.history) > 1:
            self.history.pop()
            self.vertices = self.history[-1].copy() if self.history else []
            self.selected_vertex = None
            self.update_info()
            self.redraw_canvas()
            return True
        return False

    # ==================== ОБРАБОТКА КАСАНИЙ ====================
    def on_touch_down(self, widget, touch):
        """Обработка касания экрана"""
        # Игнорируем касания на кнопках
        if widget.collide_point(*touch.pos):
            x, y = touch.pos

            # Проверяем, попали ли по существующей вершине
            for i, (vx, vy) in enumerate(self.vertices):
                if abs(vx - x) < 20 and abs(vy - y) < 20:
                    self.selected_vertex = i
                    self.dragging = True
                    self.redraw_canvas()
                    return True

            # Добавляем новую вершину
            self.vertices.append((x, y))
            self.save_state()
            self.selected_vertex = len(self.vertices) - 1
            self.update_info()
            self.redraw_canvas()
            return True
        return False

    def on_touch_move(self, widget, touch):
        """Обработка перемещения пальца"""
        if self.dragging and self.selected_vertex is not None:
            x, y = touch.pos
            self.vertices[self.selected_vertex] = (x, y)
            self.redraw_canvas()
            return True
        return False

    def on_touch_up(self, widget, touch):
        """Обработка окончания касания"""
        if self.dragging:
            self.dragging = False
            self.save_state()
            self.update_info()
            return True
        return False

    # ==================== ОТРИСОВКА ====================
    def redraw_canvas(self):
        """Полная перерисовка холста"""
        self.canvas_widget.canvas.clear()

        # Рисуем сетку
        if self.show_grid:
            with self.canvas_widget.canvas:
                Color(*self.colors['grid'])
                grid_size = 40
                width, height = self.canvas_widget.size

                # Вертикальные линии
                for x in range(0, int(width), grid_size):
                    Line(points=[x, 0, x, height], width=0.5)

                # Горизонтальные линии
                for y in range(0, int(height), grid_size):
                    Line(points=[0, y, width, y], width=0.5)

        # Рисуем линии между вершинами
        if len(self.vertices) >= 2:
            with self.canvas_widget.canvas:
                Color(*self.colors['edge'])

                # Все стороны
                for i in range(len(self.vertices)):
                    x1, y1 = self.vertices[i]
                    x2, y2 = self.vertices[(i + 1) % len(self.vertices)]
                    Line(points=[x1, y1, x2, y2], width=2.5)

        # Рисуем вершины
        for i, (x, y) in enumerate(self.vertices):
            with self.canvas_widget.canvas:
                color = self.colors['vertex_selected'] if i == self.selected_vertex else self.colors['vertex']
                Color(*color)
                Ellipse(pos=(x-10, y-10), size=(20, 20))

                # Номер вершины
                Color(1, 1, 1, 1)

        # Рисуем углы
        if self.show_angles and len(self.vertices) >= 3:
            for i in range(len(self.vertices)):
                A = self.vertices[(i-1) % len(self.vertices)]
                B = self.vertices[i]
                C = self.vertices[(i+1) % len(self.vertices)]

                angle = self.calculate_angle(A, B, C, self.angle_mode)
                color_idx = i % len(self.colors['angle'])

                # Текст угла
                with self.canvas_widget.canvas:
                    Color(*self.colors['angle'][color_idx])

                # Простая дуга
                bx, by = B
                with self.canvas_widget.canvas:
                    Line(circle=(bx, by, 25, 0, 60), width=2)

        # Подписи длин сторон
        if self.show_sides and len(self.vertices) >= 2:
            lengths = self.calculate_side_lengths()
            for i, length in enumerate(lengths):
                x1, y1 = self.vertices[i]
                x2, y2 = self.vertices[(i + 1) % len(self.vertices)]
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                with self.canvas_widget.canvas:
                    Color(0.9, 0.9, 0.9, 1)

        self.update_info()

    def update_info(self):
        """Обновляет информационную панель"""
        if not self.vertices:
            info = "[size=18][b]Геометрический визуализатор[/b][/size]\nКоснитесь экрана для добавления вершин"
        else:
            n = len(self.vertices)
            if n < 3:
                info = f"[size=16]Вершин: {n}[/size]\nДобавьте ещё {3-n} вершину(ы)"
            else:
                # Вычисляем углы
                angles = []
                for i in range(n):
                    A = self.vertices[(i-1) % n]
                    B = self.vertices[i]
                    C = self.vertices[(i+1) % n]
                    angles.append(self.calculate_angle(A, B, C, self.angle_mode))

                total_angle = sum(angles)
                expected_sum = (n - 2) * 180 if self.angle_mode == "internal" else (n + 2) * 180

                info = f"[size=16]{self.get_polygon_type()}[/size]\n"
                info += f"Вершин: {n}, Углов: {total_angle:.1f}°\n"
                info += f"Ожидаемая сумма: {expected_sum}°\n"

                if n == 4:
                    opposite1 = angles[0] + angles[2]
                    opposite2 = angles[1] + angles[3]
                    info += f"∠1+∠3={opposite1:.1f}°, ∠2+∠4={opposite2:.1f}°\n"
                    if abs(opposite1 - 180) < 1 and abs(opposite2 - 180) < 1:
                        info += "[color=00ff00]✓ Вписанный[/color]"

        self.info_label.text = info

    # ==================== УПРАВЛЕНИЕ ====================
    def reset_app(self, instance):
        """Сброс приложения"""
        self.vertices.clear()
        self.history.clear()
        self.selected_vertex = None
        self.update_info()
        self.redraw_canvas()

    def toggle_angles(self, instance):
        """Переключение отображения углов"""
        self.show_angles = not self.show_angles
        instance.state = 'down' if self.show_angles else 'normal'
        self.redraw_canvas()

    def toggle_sides(self, instance):
        """Переключение отображения сторон"""
        self.show_sides = not self.show_sides
        instance.state = 'down' if self.show_sides else 'normal'
        self.redraw_canvas()

    def toggle_grid(self, instance):
        """Переключение отображения сетки"""
        self.show_grid = not self.show_grid
        instance.state = 'down' if self.show_grid else 'normal'
        self.redraw_canvas()

    def load_example(self, instance):
        """Загрузка примера фигуры"""
        self.vertices.clear()

        # Пример треугольника
        center_x = self.canvas_widget.width / 2
        center_y = self.canvas_widget.height / 2

        if self.canvas_widget.width == 100:  # Если размеры еще не определены
            center_x, center_y = 400, 300

        self.vertices.append((center_x, center_y + 100))
        self.vertices.append((center_x - 86.6, center_y - 50))
        self.vertices.append((center_x + 86.6, center_y - 50))

        self.save_state()
        self.update_info()
        self.redraw_canvas()

# Запуск приложения
if __name__ == '__main__':
    GeometryVisualizerKivy().run()