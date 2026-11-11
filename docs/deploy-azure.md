# Deploy no Azure (bônus)

O enunciado não pede deploy. Fiz porque queria deixar uma demo acessível sem instalar nada: https://emporio-frontend.niceocean-f7122f5d.brazilsouth.azurecontainerapps.io

As imagens são publicadas no GHCR pelo GitHub Actions e rodam em dois apps no Azure Container Apps.

```
navegador --> emporio-frontend (público, Next.js) --> emporio-backend (interno, FastAPI) --> Gemini
```

Só o frontend tem URL pública. O backend usa ingress interno, então a API não pode ser chamada de fora, e a cota do Gemini só é gasta por quem passa pela interface.

## 1. Testar o Docker localmente

Na raiz, com o Docker aberto:

```powershell
docker compose up --build
```

Abra http://localhost:3000 e converse antes de publicar.

## 2. Publicar as imagens

O workflow `.github/workflows/publish.yml` roda a cada push na `main` que altere `backend/` ou `frontend/` e gera:

- `ghcr.io/gustavosousa777/emporio-backend`
- `ghcr.io/gustavosousa777/emporio-frontend`

Pacotes novos nascem privados. Para cada um: GitHub, perfil, Packages, o pacote, Package settings, Change visibility, Public. As imagens não têm segredo. A chave do Gemini entra só como variável no Azure.

## 3. Criar os apps

Com o Azure CLI instalado (`az --version`):

```powershell
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

Reaproveitei o ambiente que eu já tinha de outro projeto. Veja os seus com `az containerapp env list -o table`. Se não tiver nenhum, crie:

```powershell
$RG = "rg-emporio"
$AMBIENTE = "env-emporio"
$REGIAO = "brazilsouth"
az group create --name $RG --location $REGIAO
az containerapp env create --name $AMBIENTE --resource-group $RG --location $REGIAO
```

Backend, lendo a chave do `backend/.env` para não digitá-la no terminal:

```powershell
$CHAVE = ((Get-Content backend\.env | Where-Object { $_ -match '^GEMINI_API_KEY=' }) -replace '^GEMINI_API_KEY=','').Trim()
az containerapp create --name emporio-backend --resource-group $RG --environment $AMBIENTE --image ghcr.io/gustavosousa777/emporio-backend:latest --target-port 8000 --ingress internal --cpu 0.5 --memory 1.0Gi --min-replicas 1 --max-replicas 1 --secrets "gemini-key=$CHAVE" --env-vars GEMINI_API_KEY=secretref:gemini-key TRUST_PROXY=true RATE_LIMIT_PER_MINUTE=30
```

Frontend:

```powershell
az containerapp create --name emporio-frontend --resource-group $RG --environment $AMBIENTE --image ghcr.io/gustavosousa777/emporio-frontend:latest --target-port 3000 --ingress external --cpu 0.25 --memory 0.5Gi --min-replicas 1 --max-replicas 1 --env-vars "BACKEND_URL=http://emporio-backend"
```

Endereço público:

```powershell
az containerapp show --name emporio-frontend --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv
```

A saída do `create` pode mostrar as variáveis de ambiente sem valor. Confira com `az containerapp show --name emporio-backend --resource-group $RG --query "properties.template.containers[0].env"`.

## 4. Operação

Logs:

```powershell
az containerapp logs show --name emporio-backend --resource-group $RG --tail 50
```

Nova versão depois de um push. Use o hash do commit, porque repetir a tag `latest` não cria revisão nova:

```powershell
az containerapp update --name emporio-backend --resource-group $RG --image ghcr.io/gustavosousa777/emporio-backend:HASH_DO_COMMIT
```

## Limitações

- O disco do Container Apps é efêmero. Se o backend reiniciar, o histórico de conversas e o índice com embeddings são refeitos e as conversas antigas somem.
- O backend roda com uma réplica, porque o histórico fica em SQLite local.
- A cota diária do Gemini é uma só. Se acabar, o failover troca de modelo, e se todos acabarem a resposta é o aviso de instabilidade.
- O limite de mensagens por IP usa o IP que a interface repassa no `X-Forwarded-For`.
