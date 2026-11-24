# Jules Desktop Pet + Antigravity Bridge + OctoSwarm

Um pet de área de trabalho em **pixel art (`24×22`, 4 tentáculos)** para Windows inspirado no mascote polvo roxo do **Jules** (`jules.google`), integrado em tempo real ao **Google Antigravity** com personalidade de sessão e orquestração visual de subagentes (**OctoSwarm**).

## Como rodar o Pet

- **Modo rápido (sem abrir janela de terminal):** dê um duplo clique em `start_jules.bat`.
- **Pelo terminal:**
  ```powershell
  uv run main.py
  ```

## Integração com o Antigravity (Plugin `jules-pet-bridge`)

O projeto inclui o plugin oficial em `plugins/jules-pet-bridge/` (`plugin.json` + `hooks.json` + `scripts/hook_bridge.py` em Python stdlib puro):

1. Copie a pasta `plugins/jules-pet-bridge/` para `~/.gemini/config/plugins/jules-pet-bridge/` (ou `.agents/plugins/jules-pet-bridge/` no seu workspace).
2. Inicie o Jules Desktop Pet (`start_jules.bat` ou `uv run main.py`).
3. O pet escuta em `127.0.0.1:18765` (configurável via `JULES_PET_PORT`) e lê `transcript.jsonl` automaticamente quando os hooks disparam.
   - Se o pet estiver fechado, `hook_bridge.py` faz *fail-open* em menos de 100 ms sem atrasar o Antigravity.

## Funcionalidades & Interações

- **Expressões e Status em Tempo Real:** o balão flutuante mostra o que o Antigravity está fazendo (leitura, edição, terminal, raciocínio, erro com tinta preta e suor quando o contexto passa de 75%).
- **OctoSwarm (Subagentes na Tela):** quando o Antigravity dispara subagentes, até **5 clones coloridos** saltam perto do Jules principal (excedentes aparecem no badge `+N`), interagem em paralelo e fazem **toca-aqui** visual (sem som) ao concluir antes de desaparecer.
- **Aprovação pelo Pet (opcional):** ative **Aprovação pelo Pet** no menu da bandeja (e `JULES_PET_APPROVAL_BRIDGE=1` no ambiente) para aprovar ou bloquear `run_command` direto pelos botões `[Permitir]` / `[Bloquear]` no balão do Jules.
- **Modo Click-Through:** ative via bandeja ou pelo atalho `Ctrl+Shift+J` para que o Jules e os clones não bloqueiem cliques na IDE.
- **Interações diretas:** arrastar/jogar pela tela, clique (pulinho + estrelinhas), duplo clique (corações), carinho ao passar o mouse, e menu completo no clique direito / bandeja do Windows.

## Testes

```powershell
$env:QT_QPA_PLATFORM="offscreen"; uv run pytest -v
```
