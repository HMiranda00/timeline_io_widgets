# Timeline In/Out Widgets

Uma extensão para Blender 5.0 que adiciona handles visuais arrastáveis diretamente na timeline para definir os frames de entrada e saída.

![Concept](https://via.placeholder.com/800x200/1a1a2e/16a085?text=In/Out+Handles+on+Timeline)

## Funcionalidades

- **Handles Visuais Arrastáveis**: Marcadores verdes (IN) e vermelhos (OUT) diretamente na timeline
- **Arrastar para Ajustar**: Clique e arraste os handles para ajustar o frame range
- **Overlay de Range**: Área levemente destacada entre os pontos de entrada e saída
- **Feedback Visual**: Handles mudam de cor ao passar o mouse ou arrastar
- **Labels Informativos**: Mostra o número do frame ao interagir com os handles
- **Multi-Editor**: Funciona em todos os editores de animação:
  - Dope Sheet
  - Graph Editor
  - NLA Editor
  - Video Sequence Editor

## Instalação

### Método 1: Instalar como Extensão (Recomendado para Blender 5.0+)

1. Baixe ou clone este repositório
2. No Blender, vá em **Edit → Preferences → Add-ons**
3. Clique na seta ao lado de "Install..." e selecione **Install from Disk**
4. Navegue até a pasta da extensão e selecione-a
5. Ative a extensão marcando a checkbox

### Método 2: Instalação Manual

1. Copie a pasta `timeline_io_widgets` para o diretório de extensões:
   - **Windows**: `%APPDATA%\Blender Foundation\Blender\5.0\extensions\`
   - **macOS**: `~/Library/Application Support/Blender/5.0/extensions/`
   - **Linux**: `~/.config/blender/5.0/extensions/`
2. Reinicie o Blender
3. Ative a extensão em Preferences

## Uso

Após instalado, você verá handles visuais nas bordas do frame range em qualquer editor de animação:

### Handles

| Handle | Cor | Função |
|--------|-----|--------|
| **IN** (esquerda) | 🟢 Verde | Define o frame inicial |
| **OUT** (direita) | 🔴 Vermelho | Define o frame final |

### Interação

1. **Hover**: Passe o mouse sobre um handle para destacá-lo
2. **Arrastar**: Clique e arraste para ajustar o frame
3. **Cancelar**: Pressione `ESC` ou botão direito para cancelar o arraste

### Toggle

Para ativar/desativar os widgets:
- Vá em **View → In/Out Frame Handles** em qualquer editor de animação

## Aparência Visual

```
Timeline
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  ▶ IN: 1                              OUT: 250 ◀       │
│  █                                              █       │
│  █   [====== área do range destacada ======]   █       │
│  █                                              █       │
│  ▼                                              ▼       │
└─────────────────────────────────────────────────────────┘
```

## Compatibilidade

- **Blender**: 5.0 e posterior
- Usa o novo formato de Extensão introduzido no Blender 4.2+
- Usa o módulo `gpu` moderno (não o deprecated `bgl`)

## Mudanças na API do Blender 5.0

Esta extensão foi desenvolvida especificamente para o Blender 5.0, considerando:

- Uso do `blender_manifest.toml` em vez do deprecated `bl_info`
- Uso do módulo `gpu` e `gpu_extras` para desenho
- Uso de `draw_handler_add` com 'POST_PIXEL' para overlays 2D
- Compatibilidade com o sistema de View2D para conversão de coordenadas

## Customização

### Cores

Você pode modificar as cores dos handles editando as variáveis no arquivo `__init__.py`:

```python
# Cores do handle IN (verde)
in_color_normal = (0.2, 0.8, 0.3, 0.7)
in_color_hover = (0.3, 1.0, 0.4, 0.9)

# Cores do handle OUT (vermelho)
out_color_normal = (0.9, 0.3, 0.2, 0.7)
out_color_hover = (1.0, 0.4, 0.3, 0.9)
```

## Licença

GPL-3.0-or-later - Veja [LICENSE](LICENSE) para detalhes.

## Contribuições

Contribuições são bem-vindas! Abra uma issue ou pull request no repositório.
