# IA própria com pesquisa e integração GitHub

Painel independente do ChatGPT, em português, construído com FastAPI, Ollama e SearXNG. **Versão inicial (MVP)**.

## Funcionalidades
- Conversa com modelo local via Ollama (sem custo por token; exige recursos da VPS).
- Busca web via SearXNG local e leitura de resultados.
- Lista de repositórios autorizados, leitura de arquivos do GitHub.
- IA pode **propor** alterações. As alterações só são gravadas no GitHub após aprovação manual no painel.
- Proteção de API por senha, GitHub token somente no servidor, histórico de chat no navegador.

## Instalação

1. Instale Docker e Docker Compose na VPS.
2. Clone este repositório: `git clone https://github.com/TFERRE21/IA.git && cd IA`.
3. Execute `cp .env.example .env`, edite as variáveis e use uma senha longa.
4. Gere um token **fine-grained** em https://github.com/settings/personal-access-tokens/new com **Contents: Read and write**, apenas nos repositórios necessários. Para listar os repositórios permitidos, informe-os em `GITHUB_ALLOWED_REPOS`, separados por vírgula.
5. Inicie: `docker compose up -d --build`.
6. Baixe o modelo: `docker compose exec ollama ollama pull qwen2.5:3b`.
7. Configure proxy reverso HTTPS autenticado (Caddy, Nginx ou proxy existente) para `http://127.0.0.1:8095`. **Não exponha o HTTP sem TLS na internet.**

Teste localmente: `curl http://127.0.0.1:8095/health`.

## Como usar
- Entre no painel com a senha do .env.
- Peça, por exemplo: “Liste meus repositórios” ou “Leia README.md do repositório TFERRE21/IA”.
- Para alterar um arquivo: “Proponha uma alteração para ...”. Confirme a proposta no painel após revisar o conteúdo; só então é escrito no GitHub.
- A API de GitHub exige token com acesso ao repositório selecionado.
- Nenhum comando arbitrário de shell/deploy é executado nesta versão.

## Cuidados
- Nunca inclua chaves no chat ou em commits. A aprovação de alteração mostra o conteúdo integral, então revise antes de aprovar.
- A gravação usa o SHA atual do arquivo e impede sobrescrita se houve mudança desde a proposta.
- Este MVP faz commit diretamente no branch padrão **apenas após aprovação**. Para produção, recomenda-se evoluir para branches e Pull Requests, auditoria e autenticação por usuário.
- Pesquisas web podem conter conteúdo malicioso: os resultados são tratados como dados, não como instruções.
- Se sua VPS tiver outros serviços importantes, acompanhe RAM e CPU do Ollama e configure limites antes de usar continuamente.
- O SearXNG pode sofrer bloqueios dos motores externos e não garante cobertura equivalente à pesquisa do ChatGPT.

## Estúdio de imagens e vídeos (adicionado)

- Geração de imagens PNG com ComfyUI via API, utilizando um checkpoint compatível com os nós padrão.
- Vídeo MP4 em formato **storyboard de imagens estáticas sequenciais** (sem movimento generativo, personagens animados, voz ou trilha nesta versão).
- Fila persistente no SQLite: tarefas pendentes retornam à fila após reiniciar; uma tarefa por vez para reduzir risco de sobrecarga.
- Progresso por cena, status, erros, cancelamento e download na interface.
- Configure `COMFYUI_URL` como endereço privado do ComfyUI acessível da VPS e `COMFYUI_CHECKPOINT` como nome do checkpoint **já instalado no ComfyUI**.
- **Nunca exponha o ComfyUI sem autenticação à internet**. Use rede privada/VPN, proxy autenticado ou túnel seguro.
- O ComfyUI não é instalado neste Compose porque normalmente precisa rodar no computador com GPU. A API aceita acesso remoto privado.
- `MEDIA_MAX_WIDTH` e `MEDIA_MAX_HEIGHT` controlam a resolução máxima; a GPU pode precisar de valores menores.
- O sistema possui limites de duração, dimensões, tamanho de prompt e fila para proteção de recursos, não bloqueios de conteúdo por geografia.
- Para gerar animações verdadeiras, vídeo com áudio e sincronização, será necessário adicionar um motor de vídeo específico e dimensionar o hardware.
- Configure limites Docker e monitore o uso da VPS. Não há garantia de execução sem travamentos; falhas são registradas no painel.

## Erro ENOENT /app/package.json na plataforma de hospedagem

Este repositório **não é Node.js**. Caso a plataforma apresente `npm error ENOENT /app/package.json`, ela selecionou um *buildpack* Node incorretamente. Não execute `npm install` e não crie um `package.json` vazio: isso não inicializa o FastAPI.

Na configuração do projeto `ia`, selecione **Dockerfile** como método de construção, com contexto `.`, arquivo `Dockerfile`, porta interna `8000`, e desative os comandos automáticos de instalação/inicialização Node.js. Defina as variáveis do `.env.example` como segredos na plataforma. Reimplante reconstruindo a imagem. O health check disponível é `GET /health`.

Se a hospedagem não aceitar Dockerfile, use SSH com Docker Compose para executar o projeto separadamente. **Atenção:** o Compose atual vincula a porta `8095` apenas à interface `127.0.0.1`; configure HTTPS/proxy reverso para acessá-la remotamente. Não remova os containers de outros projetos.

Diagnóstico via SSH:
```bash
docker compose ps
docker compose logs --tail=80 ai
curl -fsS http://127.0.0.1:8095/health
```

## Hospedagem que obriga Node.js (erro package.json ENOENT)

O repositório agora também contém `package.json` e `server.js` para hospedagem Node.js sem necessidade de alterar buildpack.

- Runtime: **Node.js 18 ou superior**.
- Install: `npm install` (sem bibliotecas externas).
- Start: `npm start` ou `node server.js`.
- Porta: lê `PORT` do painel (padrão 3000). Health: `GET /health`.
- Arquivos de interface: `static/index.html`.
- Configure as variáveis de ambiente no painel: `PANEL_PASSWORD`, `GITHUB_TOKEN`, `GITHUB_ALLOWED_REPOS`, `OLLAMA_URL`, `OLLAMA_MODEL`, `SEARXNG_URL`, `COMFYUI_URL`, `COMFYUI_CHECKPOINT`.
- Se a hospedagem recriar o sistema de arquivos a cada deploy, monte um volume persistente e defina `DATA_DIR` apontando para esse volume. Sem persistência, o histórico de propostas e imagens poderá desaparecer.
- A versão Node inclui painel, chat Ollama, pesquisa web (com SearXNG configurado), GitHub com aprovação e geração **de imagens** ComfyUI. A geração de vídeo MP4 do módulo Python/FFmpeg **não está disponível na modalidade Node** e retorna uma mensagem explícita. Para vídeos storyboard utilize Docker Compose.
- O contêiner Node não instala nem inicia Ollama, SearXNG ou ComfyUI: eles precisam estar acessíveis nos endereços configurados. Em particular, `localhost` dentro do contêiner não é a VPS nem a GPU Windows.
- Restrinja o painel com HTTPS; não exponha chaves no frontend. Os endpoints usam autenticação HTTP Basic e devem ser acessados apenas por HTTPS.
- **Não basta publicar no GitHub**: o gerenciador de deploy precisa atualizar o código (redeploy/rebuild). Se ainda surgir erro `package.json`, confirme URL do repositório e branch main vinculados ao serviço `ia`, o diretório raiz e a sincronização do último commit.
