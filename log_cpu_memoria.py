import psutil
import time
import logging
from datetime import datetime
import GPUtil

# Configuração do logging
logging.basicConfig(filename='consumo.log', level=logging.INFO, format='%(message)s')

def get_system_usage():
    # Uso de CPU em porcentagem
    cpu_percent = psutil.cpu_percent(interval=1)

    # Uso de memória
    mem = psutil.virtual_memory()
    mem_total = mem.total / (1024 ** 3)  # Convertendo para GB
    mem_used = mem.used / (1024 ** 3)
    mem_percent = mem.percent

    # Uso de disco
    disk = psutil.disk_usage('/')
    disk_total = disk.total / (1024 ** 3)  # Convertendo para GB
    disk_used = disk.used / (1024 ** 3)
    disk_percent = disk.percent

    # Uso de rede
    net = psutil.net_io_counters()
    net_sent = net.bytes_sent / (1024 ** 2)  # Convertendo para MB
    net_recv = net.bytes_recv / (1024 ** 2)

    # Uso de GPU
    gpus = GPUtil.getGPUs()
    if gpus:
        gpu = gpus[0]  # Monitorando a primeira GPU
        gpu_load = gpu.load * 100  # Uso da GPU em porcentagem
        gpu_mem_total = gpu.memoryTotal / 1024  # Convertendo para GB
        gpu_mem_used = gpu.memoryUsed / 1024
        gpu_mem_percent = gpu.memoryUtil * 100  # Uso de memória da GPU em porcentagem
    else:
        gpu_load = None
        gpu_mem_total = None
        gpu_mem_used = None
        gpu_mem_percent = None

    # Timestamp atual
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Criar um dicionário com as informações
    usage = {
        'timestamp': timestamp,
        'cpu_percent': cpu_percent,
        'mem_total_gb': mem_total,
        'mem_used_gb': mem_used,
        'mem_percent': mem_percent,
        'disk_total_gb': disk_total,
        'disk_used_gb': disk_used,
        'disk_percent': disk_percent,
        'net_sent_mb': net_sent,
        'net_recv_mb': net_recv,
        'gpu_load': gpu_load,
        'gpu_mem_total_gb': gpu_mem_total,
        'gpu_mem_used_gb': gpu_mem_used,
        'gpu_mem_percent': gpu_mem_percent
    }

    return usage

def log_usage(usage):
    # Formatar a mensagem de log
    log_message = (
        f"{usage['timestamp']}, "
        f"CPU: {usage['cpu_percent']}%, "
        f"Memória: {usage['mem_used_gb']:.2f}GB/{usage['mem_total_gb']:.2f}GB ({usage['mem_percent']}%), "
        f"Disco: {usage['disk_used_gb']:.2f}GB/{usage['disk_total_gb']:.2f}GB ({usage['disk_percent']}%), "
        f"Rede Enviada: {usage['net_sent_mb']:.2f}MB, "
        f"Rede Recebida: {usage['net_recv_mb']:.2f}MB"
    )

    # Incluir informações da GPU se disponíveis
    if usage['gpu_load'] is not None:
        gpu_message = (
            f", GPU: {usage['gpu_load']:.1f}%, "
            f"Memória GPU: {usage['gpu_mem_used_gb']:.2f}GB/{usage['gpu_mem_total_gb']:.2f}GB ({usage['gpu_mem_percent']:.1f}%)"
        )
        log_message += gpu_message

    # Verificar se algum recurso excede 85%
    alerts = []
    if usage['cpu_percent'] > 85:
        alerts.append("ALERTA: CPU acima de 85%")
    if usage['mem_percent'] > 85:
        alerts.append("ALERTA: Memória acima de 85%")
    if usage['disk_percent'] > 85:
        alerts.append("ALERTA: Disco acima de 85%")
    if usage['gpu_load'] is not None and usage['gpu_load'] > 85:
        alerts.append("ALERTA: GPU acima de 85%")
    if usage['gpu_mem_percent'] is not None and usage['gpu_mem_percent'] > 85:
        alerts.append("ALERTA: Memória da GPU acima de 85%")

    # Se houver alertas, adicionar à mensagem
    if alerts:
        alert_message = "\n" + "\n".join(alerts)
        # Tornar o alerta mais chamativo
        alert_message = f"\n{'!'*50}{alert_message}\n{'!'*50}"
        log_message += alert_message

    # Registrar a mensagem
    logging.info(log_message)
    print(log_message)  # Opcional: imprimir no console

def main():
    try:
        while True:
            usage = get_system_usage()
            log_usage(usage)
            time.sleep(1)  # Intervalo de 1 segundo entre as medições
    except KeyboardInterrupt:
        print("Monitoramento interrompido pelo usuário.")

if __name__ == '__main__':
    main()
