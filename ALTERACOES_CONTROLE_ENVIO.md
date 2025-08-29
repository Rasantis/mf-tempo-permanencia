# ALTERAÇÕES: CONTROLE DE ENVIO POR REGISTRO INDIVIDUAL

## PROBLEMA IDENTIFICADO

O sistema anterior utilizava controle por **data/hora** para determinar quais registros de tempo de permanência deviam ser enviados para a API. Isso causava o seguinte problema:

- Se durante um lote de envios algumas requisições falhassem, os registros não enviados ficavam **perdidos**
- O controle por timestamp não permitia reenvio de registros específicos que falharam
- Não havia garantia de que todos os eventos seriam enviados

## SOLUÇÃO IMPLEMENTADA

Implementado controle **por registro individual** usando um campo `enviado` na tabela:

### 1. ALTERAÇÕES NA ESTRUTURA DO BANCO

**Campo adicionado**: `enviado INTEGER DEFAULT 0`

- `0` = Registro não enviado
- `1` = Registro enviado com sucesso

### 2. ARQUIVOS MODIFICADOS

#### A) Estrutura de Banco (CREATE TABLE)
- `permanence_tracker.py:43-65` - Adicionado campo e verificação de compatibilidade
- `yolo16_v4.py:94-108` - Adicionado campo e verificação de compatibilidade  
- `yolo8_v13.py:65-79` - Adicionado campo e verificação de compatibilidade
- `yolo8_v15.py:65-79` - Adicionado campo e verificação de compatibilidade

#### B) Inserção de Registros (INSERT)
- `permanence_tracker.py:181-183` - INSERT com `enviado = 0`
- `yolo16_v4.py:475-479` - INSERT com `enviado = 0`
- `yolo8_v15.py:481-482` - INSERT com `enviado = 0`

#### C) API de Envio
- `api_tempopermanencia.py` - **REESCRITO COMPLETAMENTE**
  - Removida lógica de controle por timestamp
  - Implementada busca por `enviado = 0`
  - Marcação individual como enviado após sucesso

### 3. FUNCIONAMENTO ATUAL

#### Fluxo de Dados:
1. **Geração**: Registros criados com `enviado = 0`
2. **Busca**: API seleciona apenas `WHERE enviado = 0`
3. **Envio**: Tentativa de envio para cada registro
4. **Marcação**: Se sucesso, `UPDATE enviado = 1 WHERE id = ?`
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

O sistema é **100% compatível** com bancos existentes:
- Campo `enviado` é adicionado automaticamente se não existir
- Registros antigos ficam com `enviado = 0` (serão reprocessados)
- Não há perda de dados

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