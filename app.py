# -*- coding: utf-8 -*-
"""Entrada local para correr no PC.
No Vercel a app corre em api/index.py.
"""
from api.index import app

if __name__ == "__main__":
    print("✨ Galaxy Beats FM Super Deus iniciado")
    print("🌐 Abre: http://127.0.0.1:8250")
    app.run(host="0.0.0.0", port=8250, debug=True)
