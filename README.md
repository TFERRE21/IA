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
