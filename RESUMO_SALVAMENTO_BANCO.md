# RESUMO: COMO ESTÁ SENDO SALVO NO BANCO DE DADOS

## ✅ STATUS ATUAL - TUDO ATUALIZADO E FUNCIONANDO

### **📊 ESTRUTURA ATUAL (USO OFICIAL: `vehicle_counts`)**

```sql
CREATE TABLE vehicle_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area TEXT,
    vehicle_code INTEGER,
    count_in INTEGER,
    count_out INTEGER,
    timestamp TEXT,
    tempo_permanencia FLOAT,
    enviado INTEGER DEFAULT 0   -- 0=não enviado, 1=enviado
);
```

### **🔄 COMO É SALVO AGORA:**

#### **1. Quando um veículo sai da área de permanência:**
```sql
INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
VALUES ('area_1', 26057, 0, 1, '2024-01-15 14:30:00', 15.5, 0);
```

#### **2. Campos salvos:**
- **`area`**: "area_1" ou "area_2"
- **`vehicle_code`**: 26057 (mapeado via config)
- **`timestamp`**: Data/hora de saída
- **`tempo_permanencia`**: Tempo calculado em segundos (ex: 15.5s)
- **`count_out`**: 1 (evento de saída)
- **`enviado`**: 0 (ainda não enviado para API)

### **📍 ONDE ACONTECE O SALVAMENTO:**

#### **Script Principal `yolo16_v4.py` – contagem (entradas/saídas)**
```python
insert_exit = (
    """INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
       VALUES (?, ?, 0, 1, ?, NULL, 0)"""
)
```
- **yolo16_v4.py:255-284** – registra entradas (`count_in=1`) e saídas sem tempo (`tempo_permanencia=NULL`) assim que a linha de contagem é cruzada.

#### **PermanenceTracker: `permanence_tracker.py` – tempo de permanência**
```python
self.cursor.execute(
    '''UPDATE vehicle_counts 
       SET tempo_permanencia = ?, timestamp = ?, enviado = 0 
       WHERE id = ?''',
    (tempo_permanencia, timestamp_str, rec_id)
)
```
```python
self.cursor.execute(
    '''INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp, tempo_permanencia, enviado)
       VALUES (?, ?, 0, 1, ?, ?, 0)''',
    (area_name, vehicle_code, timestamp_str, tempo_permanencia)
)
```
- **permanence_tracker.py:178-205** – prioriza atualizar a saída mais recente que ainda não tem `tempo_permanencia`; se não existir, insere um novo registro completo.

#### **API/Envio:**
- `api_tempopermanencia.py` lê `vehicle_counts` (com `count_out=1` e `tempo_permanencia` preenchido) e marca `enviado=1` nesta tabela.

### **🔗 RELACIONAMENTO COM CONTAGEM:**

Agora centralizamos em **uma tabela**:
- **`vehicle_counts`**: registra count_in/out e também o tempo de permanência e status `enviado`.

### **🚀 FLUXO COMPLETO:**

1. Veículo entra → contagem/estado
2. Veículo permanece → cálculo interno
3. Veículo sai → salva em `vehicle_counts` com `count_out=1`, `tempo_permanencia`, `enviado=0`
4. API busca `vehicle_counts.enviado=0`
5. Sucesso → `vehicle_counts.enviado=1`

### **🔧 MAPEAMENTO VEHICLE_CODE:**

O `vehicle_code` é mapeado pela configuração:
```json
{
  "faixa1": {
    "motorcycle": 26058,
    "car": 26057,         ← Este código é salvo
    "truck": 26056,
    "bus": 26059,
    "vuc": 26060
  }
}
```

### **✅ CONFIRMAÇÃO (APÓS MIGRAÇÃO):**
- `yolo16_v4.py` garante `vehicle_counts.enviado`
- `permanence_tracker.py` salva somente em `vehicle_counts` com `enviado=0`
- `api_tempopermanencia.py` lê/marca `enviado` em `vehicle_counts`
