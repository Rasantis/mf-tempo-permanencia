import cv2
from ultralytics.utils.plotting import Annotator
from datetime import datetime

def draw_labels(im0, tracks, permanence_data, model_names):
    """
    Desenha rótulos nos objetos detectados, incluindo informações sobre o tempo de permanência.

    :param im0: Frame atual do vídeo.
    :param tracks: Lista de objetos rastreados pelo modelo.
    :param permanence_data: Dados de permanência atualizados pelo tracker.
    :param model_names: Lista de nomes das classes do modelo.
    :return: Frame atualizado com os rótulos desenhados.
    """
    annotator = Annotator(im0, line_width=2, example=str(model_names))

    for track in tracks:
        if not hasattr(track, 'boxes') or track.boxes is None:
            continue

        if track.boxes.id is None or track.boxes.xyxy is None or track.boxes.cls is None:
            continue

        for box, track_id_tensor, class_id_tensor in zip(
            track.boxes.xyxy.cpu(), track.boxes.id.cpu(), track.boxes.cls.cpu()
        ):
            x1, y1, x2, y2 = map(int, box.tolist())
            track_id = int(track_id_tensor.item())
            class_id = int(class_id_tensor.item())
            class_name = model_names[class_id]

            # Construir o rótulo com as informações básicas
            label = f"{class_name} ID:{track_id}"

            # Adicionar informações de permanência, se disponíveis
            for area_name, area_data in permanence_data.items():
                if track_id in area_data['timestamps']:
                    entry_time = area_data['timestamps'][track_id]
                    tempo_permanencia = (datetime.now() - entry_time).total_seconds()
                    label += f" {area_name}: {tempo_permanencia:.1f}s"

            # Desenhar o rótulo e a bounding box
            annotator.box_label((x1, y1, x2, y2), label, color=(255, 0, 0))

    return annotator.result()
