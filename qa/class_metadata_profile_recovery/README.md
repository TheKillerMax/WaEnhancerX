# Recuperación ART por variantes y fixture independiente de limpieza

Esta rama parte del commit `83012b298e555d8b3c87cbbec67e250582bfdb72`. Conserva las fuentes publicadas de ART17 y la matriz histórica. La workflow nueva sólo responde al primer intento de un push ordinario en `lab/classmetadata-profile-recovery-20261126`; los productores y las fuentes se fijan de nuevo. No se hace dispatch ni rerun del primer run.

## Selección que permite ejecutar

El run `45742530551` produjo 19 procesos canónicos con PASS funcional. Sus recibos y los fallos de limpieza originales se conservan. La recuperación canónica contiene quince invocaciones pendientes: baseline y candidate para API26,29,35,36,36-16k,36.1-16k y37-16k; sólo candidate para35-16k. No se invocan nuevamente los dos workloads de25,27,28,31,32,36.1,37,37.1-16k o37.2-16k ni el baseline35-16k. Los perfiles anteriores24,30,33,34 continúan excluidos.

`prior-evidence/RECOVERY_SELECTION.json` y el ledger congelado documentan esa selección. API35-16k enlaza el baseline anterior, con13 comprobaciones del workload y13 de identidad; su estado nuevo `PRIOR_PASS_NOT_REEXECUTED` no afirma una segunda ejecución ni borra la pérdida de conexión o limpieza fallida de la fase original. Su nueva fase empuja sólo driver y candidate. Todas las nonces reservadas se excluyen, incluso la candidate antigua que no llegó a ejecutarse.

La exclusión contiene 53 nonces observadas: ocho físicas/DSU, treinta reservas de ART17 y quince emisiones del run Presence `45743982684`. El ledger Presence se conserva íntegro con hash `23c4e9266688bbdf6f9e7137bda8971aa3d42eb20f841f1fc15b5cd173f15c59`. Sus emisiones permanecen consumidas aunque la primera auditoría runtime de Presence esté bloqueada; esta admisión no atribuye un PASS a esa auditoría.

## Productores separados

El job build conserva byte por byte los JAR baseline/candidate del productor histórico45699162692 y verifica su manifiesto original. Compila únicamente el driver de identidad con las nuevas fuentes. La copia del driver cambia el conjunto de targets admitidos, el rechazo del baseline35-16k y el prefijo del directorio propio; mantiene13 comprobaciones de identidad y la llamada al Main canónico. Los hashes y las identidades de ambos productores se registran por separado. Los workloads siguen siendo7 controles negativos baseline bajo34,13 controles baseline desde34 y14 controles candidate.

El build-cache crea un JAR mínimo nuevo, sin JAR canónico. Sus dos celdas API27/28 sólo observan proceso, archivos generados y recuperación del directorio propio. Un resultado nuevo podrá describir esos residuos concretos; no convierte en observado el contenido desconocido de los directorios del primer run ni vuelve a ejecutar sus workloads.

## Propiedad, transporte y limpieza

Cada fase canónica crea una raíz nueva0700 con nonce y marcador de propiedad ligado a boot y productor. El helper compartido verifica UID/GID2000, tipo, dispositivo, inode, permisos, enlaces, inventario y SHA de los archivos leídos. Sólo admite entradas concretas derivadas de los JAR declarados y los posibles descendientes oat/x86_64 de esos nombres. No presupone que esos archivos existan ni que expliquen el fallo anterior. Un descendiente desconocido, enlace, cambio de identidad, deriva de hash o cambio de boot bloquea la eliminación.

El callback de lectura conserva copias acotadas y hashes para inspección. La limpieza exige dos inventarios estables antes del primer borrado; vuelve a comprobar cada hoja, elimina nombres concretos y usa rmdir sólo para directorios vacíos. No emplea rm-rf. Si app_process no confirma retorno0, el runner retiene los archivos y el controlador debe terminar su propio grupo de procesos del emulador. La fase no recibe PASS por ese reaping; el recibo conserva el bloqueo.

La fase canónica limita el trabajo a 300 segundos y el total a 480, con 180 segundos reservados para limpieza. Cada ADB y readback recibe como máximo el plazo aún disponible. Antes de cada workload exige 90 segundos completos de trabajo; no inicia otro proceso cuando ya falta esa reserva. Un plazo agotado queda registrado como bloqueo y permite que el piloto termine el emulador propio. Estos límites acotan los comandos, sin prometer plazos absolutos para el sistema operativo ni una eliminación que el inventario no autorice.

## Auxiliares e infraestructura

El piloto usa un auxiliar ADB propio. Cambia únicamente el import de guardia respecto al auxiliar histórico; URL, tamaño/hash del ZIP, cuatro miembros, rechazo de redirecciones, exclusividad del destino y plazo90s permanecen fijados. La workflow proporciona el namespace mediante PYTHONPATH absoluto del checkout; no cambia GITHUB_REF.

El bootstrap conserva la versión, tamaño/hash, autenticación y gate APT del libpulse0 revisado. Añade sólo dos observaciones de fuentes e índices, antes del gate y después de apt-get update. El observador lee rutas fijas y acotadas, no consulta el entorno ni auth.conf, no lee contenido de índices y redacta URI privadas. Una observación parcial no sustituye la validación del paquete ni autoriza cambiar repositorios.

## Límites de interpretación

Las ocho celdas canónicas contienen cuatro perfiles ps16k simulados x86_64. La identidad exige el SDK mayor real y, desde36, SDK_INT_FULL y los dos helpers oficiales; no supone un divisor. El proceso mide su ELF64/EM_X86_64, bitness, páginas y boot y se vincula a los JAR y al productor. El cache probe tiene identidad y nonce propias. Estos resultados no califican WAEX completo, el loader productivo, Motorola/DSU ni ARM64 físico16KiB.

Los controles host anteriores no se programan otra vez. Las revisiones y los focales nuevos del adapter se conservan fuera de la workflow; cada job real debe entregar su build, runtime, recuperación y manifiesto propios.
