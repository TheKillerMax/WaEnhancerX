# Ampliación ART: diecisiete perfiles pendientes

Esta preparación amplía únicamente la prueba neutral de enlace de clases de ART. Parte del commit `1e666077571c39896b7fcadbf7c549b440d51a86` y usa la rama nueva `lab/classmetadata-profile-expansion-20261126`. No modifica las pruebas o matrices históricas ni vuelve a programar `api24`, `api30`, `api33` o `api34`, ya cualificados para este contrato.

## Dos procedencias distintas

Los JAR `baseline-art-probe.jar` y `candidate-art-probe.jar` se reutilizan íntegros del productor histórico `45699162692`, intento `1`, head `c26f330a3cbd5d26807f1b9358daa46a62d26f3a`, artefacto `15060793987`. La workflow descarga ese ID exacto con el token de lectura de Actions y el run histórico. Antes de compilar, verifica los tres miembros, sus tamaños y SHA-256, incluido el manifiesto `76c2a3397d81bab85e341fc4c7adba5618e5b27afd70b8b391bd886b64702191`. El digest del ZIP histórico se conserva como procedencia del servicio; el consumidor comprueba independientemente los miembros expandidos. No declara haber recalculado un ZIP que la acción no entrega.

El productor nuevo compila sólo `ExpansionMain.java`. Su manifiesto registra el head, run e intento nuevos, el lock nuevo, las fuentes y herramientas observadas, y el JAR del driver. Copia los JAR históricos sin reconstruirlos. Los 101 escenarios y 702 controles de cada variante pertenecen al productor histórico; no se ejecutan otra vez y nunca se atribuyen al build actual.

La única dependencia temporal del artefacto histórico es su disponibilidad en Actions. Su última lectura guardada lo encontró disponible y con vencimiento `2026-11-26T20:53:55Z`. Si el servicio ya no permite descargarlo, esta workflow se detiene antes de compilar o arrancar Android. No contiene una reconstrucción alternativa automática.

## Contrato nuevo por proceso

Cada variante carga primero el driver nuevo y después su JAR canónico. El driver comprueba el `CLASSPATH` completo y el SHA-256 de ambos JAR leídos desde el proceso que realizará el ensayo. Llama por reflexión a `org.lab.waex.qa.classmetadata.Main`; el método y las clases cualificadas continúan dentro del JAR histórico intacto.

El driver agrega trece comprobaciones de identidad separadas de los controles del trabajo: SDK mayor, UID/hardware de emulador, `Process.is64Bit()`, cabecera ELF propia, tamaño de página por `Os.sysconf(_SC_PAGESIZE)`, política de versión menor, boot previo, fingerprint, classpath exacto, ambos hashes, classloader de `Main` y boot posterior. En API 36 o superior lee `Build.VERSION.SDK_INT_FULL` del proceso y lo decodifica mediante los métodos oficiales `Build.getMajorSdkVersion` y `Build.getMinorSdkVersion`, invocados por reflexión. La falta del campo o de un helper, o una discordancia, impide iniciar el trabajo. No sintetiza ese campo desde una propiedad ni presupone su divisor.

En perfiles anteriores a API 36 no se afirma una observación de SDK menor: el perfil tiene minor cero y el recibo conserva los campos de observación como `null` y las marcas de lectura como `false`.

El encabezado ELF se guarda completo en hexadecimal y con SHA-256; el consumidor comprueba nuevamente ELF64, little endian, `EM_X86_64=62` y longitud de cabecera. El proceso debe ser `app_process64`, con UID 2000 y la misma huella y boot que observó el controller. Los campos de run y productor se etiquetan `host_expected`, para distinguir los argumentos vinculados por el host de las observaciones que realizó Android.

## Perfiles admitidos

| Perfil | Mayor | Menor | Página de aplicación | Baseline esperado | Candidato esperado |
|---|---:|---:|---:|---:|---:|
| api25 | 25 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api26 | 26 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api27 | 27 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api28 | 28 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api29 | 29 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api31 | 31 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api32 | 32 | 0 | 4096 | 7, enlace negativo esperado | 14 |
| api35 | 35 | 0 | 4096 | 13 | 14 |
| api36 | 36 | 0 | 4096 | 13 | 14 |
| api37 | 37 | 0 | 4096 | 13 | 14 |
| api36.1 | 36 | 1 | 4096 | 13 | 14 |
| api35-16k | 35 | 0 | 16384 | 13 | 14 |
| api36-16k | 36 | 0 | 16384 | 13 | 14 |
| api36.1-16k | 36 | 1 | 16384 | 13 | 14 |
| api37-16k | 37 | 0 | 16384 | 13 | 14 |
| api37.1-16k | 37 | 1 | 16384 | 13 | 14 |
| api37.2-16k | 37 | 2 | 16384 | 13 | 14 |

Los seis perfiles de 16 KiB son simulaciones x86_64 `google_apis_ps16k`. No equivalen a una prueba física ARM64 de 16 KiB. El trabajo de enlace de clases tampoco valida la aplicación completa, hooks, cuentas, UI, cargador de bibliotecas ni integración de WAEX.

## Ejecución, propiedad y recuperación

La workflow tiene únicamente `push` a esta rama, limitado a sus rutas nuevas, y exige intento 1. No define `workflow_dispatch`, `pull_request`, `create` ni `workflow_run`. Se publica como una única actualización atómica después de revisión. Un resultado parcial o ambiguo requiere leer sus recibos antes de preparar una nueva versión acotada; no se pulsa «re-run» ni se vuelve a programar toda la matriz.

El controller deriva del cualificado, con guardia explícita para la rama, evento, head y diecisiete targets nuevos. Bootstrap conserva la política revisada del runner. Las funciones del controller se compararon por AST; el cuerpo operativo se conserva, salvo la admisión de targets. Los módulos compartidos históricos y su lock completo de 21 perfiles mantienen los bytes y pines originales.

El AVD siempre es fresco y propiedad del controller. La fase crea un directorio que debe estar ausente, reserva nonces nuevas y registra el intento antes de cada ejecución. El driver y los JAR se transfieren una vez y quedan de sólo lectura. Antes de ejecutar y antes de eliminar, el host vuelve a leer el archivo completo mediante ADB sync y coteja su tamaño y SHA-256. Una identidad desconocida, una redirección o un cambio de boot impide la eliminación. La limpieza sólo usa `rm` sobre los tres nombres exactos verificados y `rmdir` sobre el directorio vacío propio. No usa eliminación recursiva.

El `finally` del controller conserva la parada y recolección del grupo de procesos del emulador que él creó. Así, incluso una fase bloqueada conserva los recibos y devuelve el control al runner desechable. El ensayo no instala APK ni modifica el teléfono, DSU, AVB, SELinux, slots o reglas de PR.

## Estado de esta preparación

La revisión local valida sintaxis Python y 54 controles focales nuevos con optimización `-O`: identidad, minor, productores, exclusiones, guardia del primer intento y limpieza con dobles explícitos. Incluye una verificación de lectura de los JAR históricos guardados. Un hallazgo posterior acotó la política de diagnósticos de javac: además de salida vacía, se reconocen exactamente los tres avisos de opciones source/target 8 obsoletas y su renglón de total, ya observados con JDK 21, en LF o CRLF. El comando debe terminar con código cero y stdout vacío; se conservan los bytes de ambos streams. Cualquier otro diagnóstico bloquea. D8 sigue requiriendo ambos streams vacíos. Ocho controles adicionales verifican exclusivamente este cambio; no se repitieron los 54 anteriores.

No se ejecutaron suites históricas, D8/javac, Android, PC ni Actions. El build real del driver y los 17 perfiles siguen pendientes hasta publicación y observación de sus recibos.

Los controles y sus resultados están en la carpeta de revisión del paquete de preparación. El README no constituye un resultado runtime ni una autorización para cambiar los pins ante un fallo.
