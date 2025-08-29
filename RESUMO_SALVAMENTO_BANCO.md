# RESUMO: COMO ESTÁ SENDO SALVO NO BANCO DE DADOS

## ✅ STATUS ATUAL - TUDO ATUALIZADO E FUNCIONANDO

### **📊 ESTRUTURA DA TABELA `vehicle_permanence`**

```sql
CREATE TABLE vehicle_permanence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigocliente INTEGER,              -- Código do cliente (ex: 1724)
    area TEXT,                         -- Nome da área (ex: "area_1") - NOVO
    vehicle_code INTEGER,              -- Código do veículo (ex: 26057)
    timestamp TEXT,                    -- Data/hora do evento
    tempo_permanencia FLOAT,           -- Tempo em segundos
    enviado INTEGER DEFAULT 0          -- 0=não enviado, 1=enviado - NOVO
);
```

### **🔄 COMO É SALVO AGORA:**

#### **1. Quando um veículo sai da área de permanência:**
```sql
INSERT INTO vehicle_permanence 
(codigocliente, area, vehicle_code, timestamp, tempo_permanencia, enviado)
VALUES (1724, 'area_1', 26057, '2024-01-15 14:30:00', 15.5, 0)
```

#### **2. Campos salvos:**
- **`codigocliente`**: 1724 (vem da configuração)
- **`area`**: "area_1" ou "area_2" (qual área detectou o veículo) 
- **`vehicle_code`**: 26057 (código correspondente ao tipo de veículo)
- **`timestamp`**: Data/hora que o veículo saiu da área
- **`tempo_permanencia`**: Tempo calculado em segundos (ex: 15.5s)
- **`enviado`**: 0 (ainda não foi enviado para API)

### **📍 ONDE ACONTECE O SALVAMENTO:**

#### **Script Principal Atual: `yolo16_v4.py`**
```python
cursor.execute(
    '''INSERT INTO vehicle_permanence 
    (codigocliente, area, vehicle_code, timestamp, tempo_permanencia, enviado)
    VALUES (?, ?, ?, ?, ?, 0)''',
    (client_code, area_detectada, vehicle_code, current_timestamp.strftime('%Y-%m-%d %H:%M:%S'), tempo)
)
```
- **Linha 475-479**: yolo16_v4.py:475-479

#### **PermanenceTracker: `permanence_tracker.py`**
```python
self.cursor.execute(
    '''INSERT INTO vehicle_permanence (codigocliente, area, vehicle_code, timestamp, tempo_permanencia, enviado)
       VALUES (?, ?, ?, ?, ?, 0)''',
    (self.client_code, area_name, vehicle_code, last_seen.strftime('%Y-%m-%d %H:%M:%S'), tempo_permanencia)
)
```
- **Linha 181-183**: permanence_tracker.py:181-183

#### **Scripts Secundários:**
- **`yolo8_v15.py`** ✅ Atualizado com campo `enviado`
- **`yolo8_v13.py`** ✅ Atualizado com campo `enviado` (acabei de corrigir)

### **🔗 RELACIONAMENTO COM CONTAGEM:**

#### **Tabela `vehicle_counts` (contagem de entrada/saída):**
```sql
INSERT INTO vehicle_counts (area, vehicle_code, count_in, count_out, timestamp)
VALUES ('area_1', 26057, 1, 0, '2024-01-15 14:30:00')
```

#### **Tabela `vehicle_permanence` (tempo de permanência):**
```sql
INSERT INTO vehicle_permanence (codigocliente, area, vehicle_code, timestamp, tempo_permanencia, enviado)
VALUES (1724, 'area_1', 26057, '2024-01-15 14:30:00', 15.5, 0)
```

**📋 IMPORTANTE**: São **duas tabelas separadas**:
- **`vehicle_counts`**: Salva eventos de entrada/saída (imediato)
- **`vehicle_permanence`**: Salva tempo de permanência (quando veículo sai da área)

### **🚀 FLUXO COMPLETO:**

1. **Veículo entra na área de contagem** → Salva em `vehicle_counts` 
2. **Veículo permanece na área** → Sistema calcula tempo
3. **Veículo sai da área** → Salva tempo em `vehicle_permanence` com `enviado = 0`
4. **API executa** → Busca registros com `enviado = 0`
5. **Envio bem-sucedido** → Marca `enviado = 1`

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

### **✅ CONFIRMAÇÃO:**

**TODOS os scripts principais agora salvam corretamente:**
- ✅ **yolo16_v4.py** (principal) - com `enviado = 0`
- ✅ **permanence_tracker.py** - com `enviado = 0` 
- ✅ **yolo8_v15.py** - com `enviado = 0`
- ✅ **yolo8_v13.py** - com `enviado = 0` (corrigido agora)

**O sistema está 100% integrado e funcionando corretamente!**