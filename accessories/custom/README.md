# Acessórios Customizados para o Jules Desktop Pet

Esta pasta permite criar e instalar **acessórios em pixel art** para o Jules sem alterar o código-fonte.

## Onde colocar seus arquivos

O Jules procura acessórios automaticamente nestas pastas (em ordem de prioridade):

1. **Pasta do usuário**:
   - Windows: `%APPDATA%\JulesDesktopPet\accessories`
   - Linux/macOS: `~/.config/jules-desktop-pet/accessories`
2. **Pasta do repositório**:
   - `<repo_root>/accessories/custom`

O ID do acessório é o nome do arquivo sem extensão (por exemplo, `monoculo.png` + `monoculo.json` cria o acessório `monoculo`).

---

## Sistema de coordenadas e âncoras

O sprite base do Jules tem **24×22 pixels lógicos**.

- **`head_top`**: centralizado horizontalmente e apoiado no topo da cabeça (`y = 2 - altura`). Ideal para chapéus, coroas e laços.
- **`eyes`**: centralizado sobre a região dos olhos (`y ≈ 7`). Ideal para óculos e monóculos.
- **`body`**: centralizado no corpo (`y ≈ 12`). Ideal para gravatas, crachás e cachecóis.
- **`full`**: sobreposição completa alinhada ao canto `(0, 0)` da grade `24×22`. Sprites com exatamente `24×22` pixels também alinham automaticamente em `(0, 0)`.

Campos opcionais de posicionamento:
- `offset_x`: deslocamento horizontal em pixels lógicos (inverte automaticamente quando o Jules olha para a esquerda).
- `offset_y`: deslocamento vertical em pixels lógicos.
- `scale_with_pet`: `true` (padrão) aplica a mesma escala nearest-neighbor do Jules; `false` mantém resolução `1x`.

---

## Formato 1: PNG transparente + JSON de metadados

Crie um PNG com fundo transparente (ex.: `24×22` ou recortado como `12×10`) e um arquivo JSON com o mesmo nome.

Exemplo `monoculo.json`:

```json
{
  "name": "Monóculo Elegante",
  "anchor": "eyes",
  "offset_x": 1,
  "offset_y": 0,
  "scale_with_pet": true
}
```

> Dica: Se você colocar apenas um `.png` sem `.json`, ele também será carregado com valores padrão (`head_top`, ou `full` se for `24×22`). Você também pode apontar para outro PNG usando `"image": "meu_sprite.png"`.

---

## Formato 2: Matriz Pixel-Art em JSON

Você pode desenhar o acessório diretamente em texto dentro de um `.json` usando `"palette"` (cores `#RGB`, `#RRGGBB` ou `#RRGGBBAA`) e `"rows"` (`.` ou espaço representam pixels transparentes).

Exemplo `coroa.json`:

```json
{
  "name": "Coroa Dourada",
  "anchor": "head_top",
  "offset_x": 0,
  "offset_y": 0,
  "scale_with_pet": true,
  "palette": {
    "Y": "#FACC15",
    "H": "#FEF08A",
    "O": "#B45309"
  },
  "rows": [
    "..Y...Y...Y..",
    ".YYH.YYH.YYH.",
    ".OOOOOOOOOOO."
  ]
}
```

---

## Formato 3: Matriz Pixel-Art em `.txt`

Para prototipagem rápida, crie um arquivo `.txt` com cabeçalho simples e a grade pixel a pixel abaixo:

```text
# Comentários começam com #
name: Laço Rosa
anchor: head_top
offset_x: 0
offset_y: 1
P=#F472B6
O=#140B29

PP.PP
POPOP
PP.PP
```

Arquivos JSON inválidos, matrizes vazias ou metadados apontando para PNGs ausentes são ignorados com segurança sem interromper o pet.
