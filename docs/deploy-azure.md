# Deploy no Azure (opcional)

O deploy não é exigido pelo desafio. Usa o mesmo caminho do projeto Telco Churn: imagens no GHCR, publicadas pelo GitHub Actions, e dois apps no Azure Container Apps.

```
navegador --> emporio-frontend (público, Next.js) --> emporio-backend (interno, FastAPI) --> Gemini
```

Só o frontend tem URL pública. O backend fica com ingress interno, então ninguém consegue chamar a API (e gastar a cota do Gemini) sem passar pela interface.

## 1. Antes de tudo

Teste local na raiz, com o Docker Desktop aberto:

```powershell
docker compose up --build
```

Abra http://localhost:3000 e converse. Só siga se isso funcionar.

## 2. Publicar as imagens

O workflow `.github/workflows/publish.yml` roda a cada push na `main` que mexa em `backend/` ou `frontend/`. Acompanhe na aba **Actions** do GitHub. Ele gera:

- `ghcr.io/gustavosousa777/emporio-backend`
- `ghcr.io/gustavosousa777/emporio-frontend`

Pacotes novos nascem privados. Para cada um: GitHub, seu perfil, **Packages**, abrir o pacote, **Package settings**, **Change visibility**, **Public**. As imagens não têm segredo: a chave do Gemini entra só como variável no Azure.

## 3. Azure

Instale o Azure CLI se precisar (`az --version`). Depois:

```powershell
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

$RG = "rg-emporio"
$ENV = "env-emporio"
$LOCAL = "brazilsouth"

az group create --name $RG --location $LOCAL
az containerapp env create --name $ENV --resource-group $RG --location $LOCAL
```

Se preferir reaproveitar o ambiente do Telco Churn, veja os nomes com `az containerapp env list -o table` e use os dele em `$RG` e `$ENV`.

Backend (ingress interno, uma réplica):

```powershell
az containerapp create --name emporio-backend --resource-group $RG --environment $ENV `
  --image ghcr.io/gustavosousa777/emporio-backend:latest `
  --target-port 8000 --ingress internal `
  --cpu 0.5 --memory 1.0Gi --min-replicas 1 --max-replicas 1 `
  --secrets gemini-key=COLE_A_CHAVE_AQUI `
  --env-vars GEMINI_API_KEY=secretref:gemini-key TRUST_PROXY=true RATE_LIMIT_PER_MINUTE=30
```

Frontend (ingress público):

```powershell
az containerapp create --name emporio-frontend --resource-group $RG --environment $ENV `
  --image ghcr.io/gustavosousa777/emporio-frontend:latest `
  --target-port 3000 --ingress external `
  --cpu 0.25 --memory 0.5Gi --min-replicas 1 --max-replicas 1 `
  --env-vars BACKEND_URL=http://emporio-backend
```

Endereço público:

```powershell
az containerapp show --name emporio-frontend --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv
```

Abra `https://` mais esse endereço. A primeira resposta pode demorar, porque o backend gera os embeddings das políticas ao subir.

## 4. Operação

Logs:

```powershell
az containerapp logs show --name emporio-backend --resource-group $RG --tail 50
```

Nova versão depois de um push (use o hash do commit, porque `latest` repetido não cria revisão):

```powershell
az containerapp update --name emporio-backend --resource-group $RG --image ghcr.io/gustavosousa777/emporio-backend:HASH_DO_COMMIT
```

## 5. Limitações do deploy

- O disco do Container Apps é efêmero. Se o backend reiniciar, o histórico de conversas e o índice com embeddings são refeitos. A interface continua funcionando, mas conversas antigas somem.
- O backend roda com uma réplica só, porque o histórico fica em SQLite local.
- A cota diária do Gemini é uma só. Se acabar, o failover troca de modelo; se todos acabarem, a resposta é o aviso de contingência.
- O limite de mensagens por IP usa o IP que a interface repassa no `X-Forwarded-For`.
