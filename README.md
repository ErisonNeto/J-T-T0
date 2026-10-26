# T0 - Regional | J&T Express

Dashboard T0 com PostgreSQL local.

## Formatos aceitos automaticamente

O importador aceita, simultaneamente:

1. **Relatório padrão/lista** — `Relatório da taxa de assinatura T0(Lista)...xlsx`
   - calcula o T0 por remessa comparando o dia do recebimento com o dia da entrega;
   - deduplica o `Número da Remessa` quando houver vários arquivos padrão.

2. **Relatório consolidado/histórico** — ex.: `T0 do dia 01 a 22 de Outubro.xlsx`
   - lê a aba de dados (normalmente `sheet0`);
   - usa `quantidade a entregar` e `entregue` para calcular o T0;
   - ignora fórmulas de coordenador do histórico e cruza responsáveis pelo `Código da base` com a Gestão.

3. **Gestão de colaboradores**
   - vincula `Código da base` ao `Estação No.` para obter R/M, S/C e UF.

### Regra de sobreposição
Se o relatório padrão e um consolidado tiverem a mesma `data + código da base`, o **relatório padrão/lista tem prioridade**. Assim o mesmo período não é somado duas vezes.

## Uso

Crie `.env`:

```env
DATABASE_URL=postgresql://postgres:SUA_SENHA@localhost:5432/jt_t0
```

Instale:

```powershell
pip install -r requirements.txt
```

Teste sem gravar:

```powershell
python importar_excel.py --dry-run
```

Importe:

```powershell
python importar_excel.py
```

Execute o dashboard:

```powershell
python -m uvicorn main:app --reload
```

Acesse `http://127.0.0.1:8000`.
