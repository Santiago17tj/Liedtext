# Letracrack

Convierte un texto en hojas manuscritas con **tu propia letra**. No imita tu estilo con IA: recorta tus trazos
de una hoja de práctica que escribes a mano y los compone en páginas (rayado, cuadriculado o blanco).

## Cómo se usa (4 pasos en pantalla)

1. **Mi letra**: crea una letra con un nombre (una por persona; usa la de otra persona solo con su permiso).
2. **Imprimir**: imprime la hoja de práctica (3 hojas) y escribe cada carácter en su cuadro.
3. **Fotos**: fotografía cada hoja entera (con los 4 cuadrados negros visibles) y súbela.
4. **Escribir**: pega el texto y descarga el PDF. `# Título` y `- lista` funcionan.

## Privacidad

El servidor **no guarda nada**. Las fotos se procesan en memoria y se descartan; la letra aprendida
(≈ 80 KB por hoja) queda en el `localStorage` del navegador y viaja al servidor solo para generar cada página.
Se puede guardar una copia en un archivo (`.letracrack.json`) para pasarla a otro dispositivo.
Ese archivo es tu letra: no lo subas a repositorios ni lo compartas sin permiso (`.gitignore` ya lo excluye).

## Ejecutar en local

```bash
pip install -r requirements-dev.txt
python run.py            # http://127.0.0.1:8765
python -m pytest tests -q
```

## Desplegar en Vercel

- Punto de entrada: `index.py` (expone `app`). Los archivos de `public/` los sirve la CDN.
- Python 3.13 (`.python-version`). Dependencias: `requirements.txt`.
- **Contraseña (recomendado):** define la variable de entorno `LETRACRACK_PASSWORD` en el proyecto de Vercel.
  Con ella, `/api/scan` y `/api/render` piden la contraseña; sin ella, cualquiera con la URL puede usar el servicio
  (consume tu cómputo). Es opcional en local.
- Cada petición de `/api/render` devuelve **una página** en JPEG (~1–2 MB) para quedar bajo el límite de respuesta;
  el PDF se arma en el navegador.

## Estructura

| Ruta | Qué hace |
| --- | --- |
| `letracrack/layout.py`, `template.py` | Hoja de práctica A4 de 96 caracteres con 4 marcas de esquina |
| `letracrack/extract.py` | Detecta marcas, corrige perspectiva, quita sombras y recorta cada carácter |
| `letracrack/profile.py` | Escaneo → glifos y validación del perfil que envía el navegador |
| `letracrack/render.py`, `paper.py` | Distribución en líneas y páginas, variantes y variación natural |
| `letracrack/app.py`, `index.py` | API Flask sin estado y contraseña opcional |
| `public/` | Interfaz (HTML + JS sin dependencias) |

## Limitaciones

- Las letras se capturan sueltas: no hay uniones entre letras. Si escribes muy ligado se notará.
- Con 3 variantes por letra se ve natural; con una sola se nota la repetición.
- Un carácter sin muestra se omite o se cambia por uno parecido, y la interfaz lo avisa.
