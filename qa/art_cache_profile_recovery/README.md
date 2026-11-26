# Fixtures nuevos de caché ART en API 27 y 28

Este módulo prepara dos ejecuciones nuevas del fixture mínimo de identidad y limpieza de caché. Su rama exclusiva es `lab/art-cache-profile-recovery-20261126`, con padre revisado `a8bea4fbf9ddefab6984e464eb24270a121cc659`. Sólo admite un `push` ordinario, primer intento, del repositorio público esperado. El workflow tiene un productor de fixture y una matriz de dos perfiles: `api27` y `api28`.

## Bloqueo observado y corrección concreta

En el run `45749434077`, el job de construcción de caché terminó antes de ejecutar javac, D8 o Android: `Existing pinned tool differs: java`. Los jobs dependientes quedaron omitidos y no emitieron claims. El informe original y su revisión se conservan byteidénticos en `prior-evidence/`. Ese informe no guardó la ruta efectiva ni el hash del archivo rechazado, por lo que no permite afirmar qué versión estaba instalada ni distinguir por sí solo ausencia de archivo de diferencia de contenido. El éxito del productor canónico en otro job del mismo run tampoco identifica el JDK del job fallido.

La identidad exacta que ahora se selecciona procede del manifiesto histórico completo `76c2a3397d81bab85e341fc4c7adba5618e5b27afd70b8b391bd886b64702191`, conservado íntegro como `JDK21_REFERENCE_MANIFEST.json`. Su sección `kotlin_toolchain.java` registra Temurin 21.0.13, runtime `21.0.13+9-LTS`, javac 21.0.13 y seis hashes de archivos del mismo JDK. El workflow pide explícitamente `21.0.13+9`, paquete JDK, arquitectura x64, mediante la acción ya fijada. Después pasa al builder `$JAVA_HOME`, que es la selección de esa acción. La variable del JDK preinstalado se usa únicamente para una observación separada anterior a la selección.

Los cuatro pins anteriores de java, javac, `android.jar` y D8 se conservan. Además se exige la identidad histórica de `release`, `lib/modules`, `lib/ct.sym` y `lib/server/libjvm.so`, junto a los cuatro metadatos SDK ya fijados. Una selección nominal de versión no equivale a superar este gate. Si la distribución no está disponible o cualquiera de los archivos difiere, se conserva el rechazo; no se actualizan pins ni se escoge automáticamente otra versión.

## Observación previa al rechazo

`jdk_observation.py` sólo lee rutas concretas. Para cada insumo conserva ruta solicitada, ruta resuelta, presencia, tipo, tamaño, SHA-256, estabilidad durante la lectura y cualquier error. También conserva un fallo de resolución de la raíz JDK o SDK y sigue intentando los demás registros. No ejecuta java ni javac para averiguar su identidad. Rechaza archivos cuyo tamaño observado supera 512 MiB y exige identidad estable de descriptor y ruta durante el hash; ese control no equivale a un límite duro de bytes leídos si un archivo creciera concurrentemente.

`build.py` guarda `selected-inputs-before-gate.json` y añade todas sus observaciones a `build-result.json` antes de validar los pins. Así, un fallo del primer archivo no oculta las observaciones de los demás. Sólo después de superar todos los pins puede invocar los compiladores. Tras construir conserva un segundo conjunto de lecturas y exige los mismos pins y raíces. Los recibos y la observación del JDK preinstalado se suben también cuando el job falla.

## Reutilización y alcance

Las fuentes publicadas del padre permanecen intactas. Se reutilizan por importación y hash sus helpers de generación de fuente, ejecución de compiladores, lectura DEX y archivos; su Java `CacheLifecycleMain.java`, el validador y `OwnedTree` permanecen byteidénticos. Los argumentos javac y D8, el tratamiento estricto de diagnósticos, la clase única, el JAR determinista y la verificación de archivos no cambian. Sólo se construye ese fixture nuevo. El manifiesto histórico completo se usa como evidencia de JDK: no autoriza descargar o reconstruir los JAR canónicos.

El runner y el piloto propios conservan el comportamiento publicado y cambian únicamente las referencias a la admisión y a los auxiliares de esta rama. `bootstrap.py` y `reviewed_adb.py` usan la guardia propia; la importación de helpers puros del padre no invoca su guardia de rama. La matriz histórica, las imágenes, el emulador, ADB, JRE de herramientas y libpulse conservan sus pins. El observador APT ya revisado se reutiliza sin cambios. No hay sustitución de variables GitHub ni modificación de constantes de módulos heredados.

El artefacto del nuevo productor contiene exclusivamente `cache-probe.jar` y su manifiesto. El runner verifica el productor actual, commit, run, intento, lock, fuentes, Java generado, clase única y hashes antes de iniciar el fixture. No hay job de construcción canónica, descarga de sus artefactos ni llamada a sus workloads.

## Nonces, proceso y recuperación

El ledger final del run anterior, `46b04ca09f3d595be909f37da9b44061c19a07aa2959e42de53c92eba2ed6a56`, registra 23 reservas nuevas únicas: ocho fases y quince variantes. Su colección está completa y no tiene colisiones ni incidencias. Junto a las 53 anteriores produce 76 nonces conocidas no reutilizables. Esta cifra procede del archivo observado, no de la cantidad esperada de jobs. No pretende inventariar todas las ejecuciones históricas ajenas a estas fuentes.

Cada perfil nuevo genera una nonce una sola vez, rechaza cualquier coincidencia antes de ADB y guarda una claim antes del efecto del fixture. La raíz nueva es exclusiva, tiene modo 0700, UID/GID 2000, nonce, boot y marcador de productor. El runner mide API, ABI, ELF, tamaño de página y boot del proceso propio. Conserva el presupuesto de trabajo de 120 segundos y el total de 240, con reserva de limpieza y gate previo al lanzamiento; no inicia otra ejecución tras un resultado ambiguo.

`OwnedTree` conserva inventarios acotados, rechaza enlaces y contenido desconocido y retiene hashes y copias antes de borrar. Sólo admite el JAR declarado y hojas concretas derivadas de su nombre bajo `oat/x86_64`, si realmente se observan. Exige dos inventarios estables y vuelve a validar cada hoja. Elimina archivos concretos y directorios vacíos; no usa borrado recursivo. Si no hay confirmación de terminación del proceso o la propiedad es ambigua, retiene la raíz y el controlador exterior recoge únicamente su AVD. Un resultado así no se presenta como limpieza verificada.

## Interpretación del resultado futuro

Los workloads canónicos de API 27 y 28 ya pasaron en el primer run; su `rmdir` histórico falló sin inventario suficiente para conocer el residuo. Estos fixtures nuevos no repiten esos workloads ni convierten retroactivamente aquella limpieza en PASS. Su resultado sólo podrá acreditar el ciclo de vida e inventario realmente observados del fixture nuevo en cada perfil x86_64 de 4 KiB. Tampoco acredita WAEX completo, integración productiva, otro Android, DSU o ARM64 físico de 16 KiB.

La preparación local no ejecuta SDK, compiladores, emuladores ni Android. Los controles host nuevos cubren únicamente la selección, retención diagnóstica y admisión que cambiaron; los 30 controles de `OwnedTree` y los 13 del adapter anterior no se programan ni repiten. Las revisiones y sus recibos se conservan fuera de las fuentes publicables. Cualquier cierre de construcción o runtime requiere sus nuevos recibos reales.
