# mf-tempo-permanencia

Contagem de veículos e **tempo de permanência** por área, a partir de câmeras
RTSP. Detecção com **YOLO (ultralytics)**, áreas definidas como polígonos
(`shapely`), persistência em SQLite e exportação para a API do cliente.

## Módulos

| Arquivo | O que faz |
|---|---|
| `yolo16_v4.py` | laço principal: lê o RTSP, detecta, conta por faixa e grava. Usa threads + `queue` para separar captura de processamento |
| `permanence_tracker.py` | `PermanenceTracker` — mede quanto tempo cada objeto permanece dentro do polígono |
| `label_manager.py` | desenho dos rótulos sobre o frame |
| `desenhar_area.py`, `desenho.py` | definição visual das áreas/faixas |
| `db.py` | acesso ao SQLite |
| `dbexport_halfhour.py`, `dbexport_consolidate.py`, `formatar_dbread.py` | exportação em janelas de 30 min e consolidação |
| `api_tempopermanencia.py` | envio para a API do cliente |
| `log_cpu_memoria.py` | monitoramento de recursos |
| `diagnostico_banco_cliente.py`, `analisar_diferencas_contagem.py`, `corrigir_nulls_tempo.py` | diagnóstico e correção de dados |

## Configuração

Um arquivo por câmera em `config/` (`camera1_config.json`, `camera2_config.json`,
`camera3_config.json`), com o código do cliente, a URL RTSP e o mapeamento de
cada faixa para os códigos de `motorcycle`, `cars`, `truck`, `bus` e `vuc`.

> **Cada câmera precisa de arquivo de configuração e diretório de exportação
> próprios.** O tutorial de instalação está em [`READEME.md`](READEME.md) — o
> nome tem um erro de digitação histórico, mantido para não quebrar referências.

Os `.bat` (`mfvc_camera1.bat` …) e os atalhos `.lnk` sobem uma câmera cada.
`mf_apagaAntigos.bat` e `mf_deleteTemp.bat` fazem a limpeza periódica.

## Branches

- `main` — a linha atual
- `rescue/wip-detached-2026-09` — estado que estava solto no diretório de
  trabalho em detached HEAD, preservado em 07/09/2026 para não se perder
