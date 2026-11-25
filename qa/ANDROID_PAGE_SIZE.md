# Identidad del tamaño de página en el laboratorio Android

## Política de observación

El laboratorio revisado contiene 21 objetivos x86_64. En API 24–28 y página esperada de 4.096 bytes, el controller obtiene directamente la cabecera ELF64 little-endian del ejecutable `/system/bin/cat` y el AUXV binario de su proceso. Exige arquitectura x86_64, cabecera válida, pares de 64 bits completos, terminador `AT_NULL`, etiquetas sin duplicados y `AT_PAGESZ == 4096`.

La lectura usa `exec-out`, el servidor ADB aislado del controller y su emulador propio. No usa PTY, permisos root ni APK. Todo error del transporte o de los datos bloquea. Se conserva el hash y tamaño de la lectura completa del ejecutable; el artefacto retiene únicamente sus primeros 64 bytes, además de los bytes y hash del AUXV.

En API 29–37 se exige que `getconf PAGE_SIZE` termine correctamente y entregue el entero decimal esperado. Un error, código 127/255, texto inválido o tamaño diferente bloquea. Ningún error moderno habilita una alternativa AUXV. Los objetivos con páginas de 16.384 bytes mantienen esta ruta moderna.

`guest-page-size-policy.json` registra qué método se seleccionó antes de ejecutarlo. `application-page-size-observation.json` registra la observación que haya terminado correctamente. La política no supone que el tamaño de página SQLite sea igual al de aplicación y no califica ARM64 físico ni DSU.

## Defecto observado y cambio V6

En el run Presence `45563525630`, attempt `1`, commit `c71790e19533295fe140b69a78c0388a19c5ace8`, los tres emuladores arrancaron. La consulta `getconf PAGE_SIZE` devolvió exactamente los mismos 35 bytes en las tres filas: `/system/bin/sh: getconf: not found\n`.

| Fila | Código registrado | Resultado V5 |
| --- | ---: | --- |
| API 24 | 255 | Bloqueada antes de instalar el APK o ejecutar ART |
| API 25 | 255 | Bloqueada antes de instalar el APK o ejecutar ART |
| API 26 | 127 | ELF/AUXV 4.096 bytes; después pasan 4 casos ART y 7 PNG |

Los tres comandos tienen `failure: null`; el SHA-256 del mensaje exacto es `4abec8b7037221d4df63573731e3a5bcda6e9de41c8ad492d76a3f3e7fbfe1b6`. V5 autorizaba su alternativa únicamente tras el código 127. Por eso el código 255 de las dos primeras filas impedía llegar a la misma prueba binaria. Esto identifica la condición que bloqueó el run; no atribuye por sí solo el código 255 a una causa interna de ADB o del shell.

V6 selecciona la prueba binaria desde el API, ABI y página revisados antes de ejecutar comandos. Elimina la dependencia de un código de salida concreto para una utilidad ausente. Conserva sin cambios el parser ELF/AUXV y el transporte binario existentes. No incorpora aceptación genérica de códigos de error.

La identidad de los tres ZIP y sus manifiestos se verifica en la evidencia independiente que acompaña al candidato. La ejecución V5 fallida permanece como tal; el cambio necesita ejecuciones Android nuevas antes de calificarse en CI.

## Controles host

Desde la raíz del checkout:

```sh
python qa/test_android_page_size.py
python -O qa/test_android_page_size.py
```

Los controles sustituyen cada invocación por fixtures host explícitos: no ejecutan ADB ni un emulador. Cubren los cinco API heredados sin `getconf`, los 16 perfiles modernos del lock, el paso del entorno aislado y del serial, el hash del ejecutable completo y la retención de su cabecera, errores de transporte, errores modernos sin alternativa, entradas ajenas y datos ELF/AUXV corruptos o truncados.

Estos resultados califican el contrato del controller. No sustituyen las pruebas de arranque ni las instrumentaciones Android del run posterior.
