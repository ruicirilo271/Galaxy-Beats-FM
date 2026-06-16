CORREÇÃO DO ERRO VERCEL

Erro:
The pattern "api/index.py" defined in `functions` doesn't match any Serverless Functions inside the `api` directory.

Causa mais comum:
- O vercel.json apontava para api/index.py dentro de "functions", mas o Vercel não encontrou esse ficheiro na raiz do projeto.
- Também pode acontecer quando o projeto ficou dentro de uma pasta extra no GitHub, por exemplo:
  galaxy_beats_super_deus_youtube_unavailable_fix/api/index.py
  em vez de:
  api/index.py

Como publicar:
1. No GitHub, a raiz do projeto tem de ter estes itens diretamente:
   api/
   static/
   templates/
   app.py
   requirements.txt
   vercel.json

2. Dentro da pasta api tem de existir:
   api/index.py

3. No Vercel, adiciona a variável:
   YOUTUBE_API_KEY=atua_chave_do_youtube

4. Faz Redeploy.

Nesta versão removi o bloco "functions" do vercel.json para o Vercel detetar automaticamente a função Python em api/index.py.
