# ALTERAÇÕES: CONTROLE DE ENVIO POR REGISTRO INDIVIDUAL

## PROBLEMA IDENTIFICADO

O sistema anterior utilizava controle por **data/hora** para determinar quais registros de tempo de permanência deviam ser enviados para a API. Isso causava o seguinte problema:

- Se durante um lote de envios algumas requisições falhassem, os registros não enviados ficavam **perdidos**
- O controle por timestamp não permitia reenvio de registros específicos que falharam
- Não havia garantia de que todos os eventos seriam enviados

## SOLUÇÃO IMPLEMENTADA

Implementado controle **por registro individual** usando um campo `enviado` na tabela principal de eventos:

### 1. ALTERAÇÕES NA ESTRUTURA DO BANCO

**Campo adicionado**: `enviado INTEGER DEFAULT 0` em `vehicle_counts`

- `0` = Registro não enviado
- `1` = Registro enviado com sucesso

### 2. ARQUIVOS MODIFICADOS

#### A) Estrutura de Banco (CREATE/ALTER TABLE)
- `yolo16_v4.py` - Garante colunas `tempo_permanencia` e `enviado` em `vehicle_counts`
- `permanence_tracker.py` - Garante `enviado` em `vehicle_counts`

#### B) Inserção de Registros (INSERT)
- `permanence_tracker.py` - INSERT em `vehicle_counts` com `count_out=1`, `tempo_permanencia`, `enviado = 0`
- Removidos INSERTs em `vehicle_permanence`

#### C) API de Envio
- `api_tempopermanencia.py` - Atualizado
  - Busca em `vehicle_counts` por `enviado = 0`, `count_out=1` e `tempo_permanencia` válido
  - Marcação individual como enviado em `vehicle_counts`

### 3. FUNCIONAMENTO ATUAL

#### Fluxo de Dados:
1. **Geração**: Registros (saída) criados em `vehicle_counts` com `enviado = 0`
2. **Busca**: API seleciona apenas `WHERE enviado = 0 AND count_out=1 AND tempo_permanencia IS NOT NULL`
3. **Envio**: Tentativa de envio para cada registro
4. **Marcação**: Se sucesso, `UPDATE vehicle_counts SET enviado = 1 WHERE id = ?`
5. **Reprocessamento**: Próxima execução ignora registros já enviados

#### Vantagens:
- ✅ **Tolerante a falhas**: Registros não enviados permanecem com `enviado = 0`
- ✅ **Reprocessamento automático**: Registros falhados são tentados novamente
- ✅ **Controle granular**: Cada evento é controlado individualmente
- ✅ **Compatibilidade**: Bancos antigos recebem o campo automaticamente
- ✅ **Sem duplicação**: Registros enviados não são reprocessados

### 4. TESTES REALIZADOS

Criado `teste_controle_envio.py` que valida:
- ✅ Criação da nova estrutura
- ✅ Inserção com campo `enviado = 0`
- ✅ Busca de registros não enviados
- ✅ Marcação como enviado
- ✅ Exclusão automática de enviados da busca
- ✅ Compatibilidade com bancos antigos

### 5. MIGRAÇÃO

- Campo `enviado` é adicionado automaticamente em `vehicle_counts` se não existir
- A tabela `vehicle_permanence` deixa de ser utilizada (não há novos INSERTs)
- Opcional: para evitar reenvio histórico após migração, alinhar `vehicle_counts.enviado` com sua política atual

### 6. MONITORAMENTO

Para verificar o status dos envios:

```sql
-- Total de registros pendentes
SELECT COUNT(*) FROM vehicle_permanence WHERE enviado = 0;

-- Total de registros enviados
SELECT COUNT(*) FROM vehicle_permanence WHERE enviado = 1;

-- Registros por status
SELECT enviado, COUNT(*) as quantidade 
FROM vehicle_permanence 
GROUP BY enviado;
```

---

## RESUMO TÉCNICO

| Aspecto | Antes | Depois |
|---------|-------|---------|
| **Controle** | Por timestamp global | Por registro individual |
| **Falhas** | Registros perdidos | Registros reprocessados |
| **Query** | `WHERE timestamp > ?` | `WHERE enviado = 0` |
| **Marcação** | Timestamp atualizado | `enviado = 1` |
| **Robustez** | Baixa | Alta |
| **Compatibilidade** | N/A | 100% backward |

**Status**: ✅ **IMPLEMENTADO E TESTADO**
