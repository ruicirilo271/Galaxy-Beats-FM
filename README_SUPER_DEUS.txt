GALAXY BEATS FM — SUPER DEUS VERCEL
===================================

Estrutura correta para Vercel:

api/index.py
static/script.js
static/style.css
static/default_cover.png
templates/index.html
app.py
requirements.txt
vercel.json
history.json

COMO PUBLICAR NO VERCEL
-----------------------
1. Envia esta pasta para o GitHub.
2. No Vercel, importa o repositório.
3. Em Settings > Environment Variables adiciona as variáveis necessárias.
4. Faz Redeploy.

VARIÁVEIS IMPORTANTES
---------------------
YOUTUBE_API_KEY=cola_a_tua_api_key_do_youtube

Sem YOUTUBE_API_KEY o painel do YouTube mostra uma mensagem e um botão para pesquisar manualmente,
mas não consegue inserir automaticamente o vídeo dentro da aplicação.

Opcional para melhores capas/biografia:
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
LASTFM_API_KEY=...

URLs das rádios:
URL_MOTARD=...
URL_RENASCENCA=...
URL_CIDADEFM=...
URL_CIDADEFM_META=https://cidade.fm/nowplaying.xml
# também podes usar CIDADEFM_META_URL com outro endpoint se a Cidade mudar o XML
URL_RADIOCIDADE=...
URL_RECORD=...
URL_ANTENA1=...

TESTAR SE A API KEY ESTÁ ATIVA
------------------------------
Abre no navegador:
/health

Deve aparecer:
"youtube_api_key_ready": true

Se aparecer false, a variável YOUTUBE_API_KEY não está configurada no Vercel
ou falta fazer Redeploy depois de a adicionar.

CORREÇÃO DO YOUTUBE
-------------------
Esta versão usa a YouTube Data API v3 com:
- videoEmbeddable=true
- regionCode=PT
- várias pesquisas: official music video, official audio e pesquisa normal
- diagnóstico no frontend quando a API key falta, é inválida ou excedeu a quota

CORRER NO PC
------------
python -m pip install -r requirements.txt
python app.py

Depois abre:
http://127.0.0.1:8250

CORREÇÃO CIDADE FM
-------------------
Esta versão tenta primeiro identificar a Cidade FM pelo endpoint próprio nowplaying.xml / XML Bauer,
e só depois usa a API externa e Shazam. Isto evita o problema em que a música aparecia como XML cru
ou deixava de identificar no Vercel.

Se a Cidade FM mudar o endpoint, adiciona no Vercel uma destas variáveis:
URL_CIDADEFM_META=https://novo-endpoint.xml
ou
CIDADEFM_META_URL=https://novo-endpoint.xml
