import cv2
import json
import numpy as np
import argparse

# Inicializar variáveis globais
drawing = False  # True se o mouse estiver pressionado
current_area = []  # Pontos atuais da área sendo desenhada
all_areas = {}  # Dicionário para armazenar todas as áreas desenhadas
area_index = 1  # Índice da área atual
""""A PRIMEIRA LINHA SEMPRE SERÁ REFERENTE A AREA 1 E A 2 LINHA SEMPRE REFERENTE A AREA2"""

# Função de callback para eventos do mouse
def draw_area(event, x, y, flags, param):
    global drawing, current_area, frame

    if event == cv2.EVENT_LBUTTONDOWN:
        if len(current_area) < 4:
            current_area.append((x, y))
            cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)
            if len(current_area) == 4:
                cv2.polylines(frame, [np.array(current_area)], isClosed=True, color=(0, 255, 0), thickness=2)
                cv2.imshow("Frame", frame)

# Função para salvar áreas em um arquivo JSON
def save_areas_to_json(file_path, areas):
    with open(file_path, 'w') as f:
        json.dump(areas, f, indent=4)

# Configurar argumentos de linha de comando
parser = argparse.ArgumentParser(description='Desenhar áreas em um vídeo e salvar as coordenadas em um arquivo JSON.')
parser.add_argument('--source', type=str, required=True, help='Caminho para o vídeo ou link do streaming.')
parser.add_argument('--output', type=str, required=True, help='Caminho de saída para salvar o arquivo JSON com as coordenadas.')
args = parser.parse_args()

# Inicializar a captura de vídeo
cap = cv2.VideoCapture(args.source)

if not cap.isOpened():
    print("Erro ao abrir o vídeo.")
    exit()

ret, frame = cap.read()
cv2.imshow("Frame", frame)
cv2.setMouseCallback("Frame", draw_area)

while True:
    cv2.imshow("Frame", frame)
    key = cv2.waitKey(1) & 0xFF

    # Se a tecla 'r' for pressionada, salvar a área atual e começar uma nova área
    if key == ord('r'):
        if len(current_area) == 4:
            all_areas[f'area_{area_index}'] = current_area
            current_area = []
            area_index += 1

    # Se a tecla 's' for pressionada, salvar todas as áreas em um arquivo JSON e sair
    elif key == ord('s'):
        if len(current_area) == 4:
            all_areas[f'area_{area_index}'] = current_area
        save_areas_to_json(args.output, all_areas)
        break

cap.release()
cv2.destroyAllWindows()
