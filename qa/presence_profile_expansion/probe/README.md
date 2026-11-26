# Presence: quince perfiles pendientes

Este APK nuevo conserva el renderer extraído y las cuatro clases Java de la fuente pública fijada en `7814908a1213d86f05ef5dc068b548d322a24d94`. Usa los cuatro casos y siete observaciones PNG ya revisados; los dos oráculos extraídos mantienen literalmente sus cuatro aserciones. El APK tiene una identidad de productor nueva.

Los seis perfiles anteriores permanecen excluidos: API24, 25, 26, 28, 34 y API35/16 KiB. Su evidencia histórica no recibe mediciones retrospectivas. El workflow de esta ampliación sólo admite api27, api29, api30, api31, api32, api33, api35, api36, api37, api36.1, api36-16k, api36.1-16k, api37-16k, api37.1-16k y api37.2-16k.

## Medición antes de los casos

La instrumentación exige API, minor y páginas esperadas. Desde API36 lee el campo real `Build.VERSION.SDK_INT_FULL` y llama por reflexión a los métodos públicos `Build.getMajorSdkVersion` y `Build.getMinorSdkVersion`. Si faltan o no concuerdan con la imagen, el ensayo falla. No se presume la codificación numérica del campo; la descomposición proviene de los helpers oficiales. Para API anteriores el campo y los helpers quedan nulos/no leídos; minor0 es una política explícita.

El proceso mide `Process.is64Bit()`, su cabecera ELF de 64 bytes desde `/proc/self/exe` (ELF64, little endian, EM_X86_64=62), su UID/PID y `Os.sysconf(_SC_PAGE_SIZE)`. Se instala y solicita instrumentación explícitamente x86_64. También lee y calcula el SHA-256 de su propio APK acotado a 2 MiB. Las mediciones se guardan en `process_identity` y no añaden casos al contador histórico de cuatro.

El productor integra commit, run y attempt en el código compilado. El supervisor exige esos mismos valores, el hash del APK, target, una nonce nueva, run_id y boot. La aplicación sólo repite el boot recibido como vínculo; **no afirma haber leído el boot**. El launcher conserva seis lecturas reales del kernel mediante ADB, antes de instalar, antes y después de instrumentar y alrededor de la limpieza. Un cambio de boot impide continuar o desinstalar.

## Casos conservados

| Caso | PNG |
|---|---|
| pureCircleRasterizesWithoutWaex | circle |
| plainAndroidViewDrawsAndClearsWhenHidden | visible, hidden |
| nativeCanvasContainsGreenDotAndClearsOffline | online, offline |
| invalidationClearsTheNativeGreenPixel | online, invalidated |

El manifiesto, la Activity, recursos, paquete `org.waex.qa.presence.host`, minSdk24 y targetSdk28 son iguales a la base. Los métodos productivos del renderer, campos, companion, cuatro clases Java y compile bindings mantienen sus bytes/proyección. El builder cambia únicamente rutas del nuevo directorio y la integración del productor. No se llama a Gradle ni se usan módulos privados.

## Ejecución y recuperación

El workflow sólo admite el primer intento de un evento push en `lab/presence-profile-expansion-20261126` del fork público exacto. Primero comprueba las fuentes y el matrix lock histórico; construye un único APK con JDK21, Kotlin2.0.20, SDK36 y las dependencias públicas ya fijadas. La clave QA efímera se elimina.

Cada uno de los quince jobs abre exclusivamente su AVD nuevo, con KVM y herramientas de los pins previos. No se reutiliza una VM ni se habilita software CPU. El launcher rechaza un paquete preexistente; instala sin reemplazo, recupera y verifica el APK instalado, y vuelve a verificarlo antes de desinstalar. La limpieza del emulator sigue el controlador histórico, que termina exclusivamente su proceso/grupo propio. Los recibos y streams se conservan ante un fallo; no hay reintento automático del ensayo.

La copia nueva de pilot cambia sólo el import del contexto y el conjunto admitido; todos los demás métodos son equivalentes a la base. Su `main` siempre recibe el `checked_lock` histórico de matrix21 desde `run_lab.py`; su lector por defecto no se usa. Bootstrap cambia únicamente el contexto de rama. Los módulos originales y sus locks quedan intactos.

## Alcance de la preparación

Los controles focales son host, con registros sintéticos y dobles de ADB explícitos. La generación de código permite comparar el renderer y oráculos con el manifiesto E ya guardado, sin ejecutar Android. No acredita compilación, renderizado, boot o páginas reales en esta ampliación. Cada perfil sólo podrá cerrarse con su nuevo recibo de ejecución y limpieza.

Los perfiles 16 KiB son simulaciones x86_64. Este ensayo no acredita hardware ARM64/16 KiB, DSU, loader Xposed, WhatsApp ni WAEX completo.


## Evidencia host anterior y delta final

Los 45 resultados host originales y su fuente se conservan como evidencia de su versión previa, identificada por hashes. La workflow final no reejecuta esa suite. El caso original fake_sdk_full dependía del divisor100000 y se sustituyó únicamente en el archivo publicado por nonpositive_sdk_full=-1, un rechazo que sigue siendo válido cualquiera que sea la codificación. Ese único caso nuevo se comprobó aisladamente; los otros44 contratos conservan sus criterios por lectura, sin una nueva ejecución de la suite. El contrato final exige el campo real, su valor positivo y los resultados de ambos helpers oficiales. La instrumentación, el parser y el workflow finales se revisan con sus nuevos pins y una comprobación focal separada del cambio de representación. Los ocho valores de nonce ya consumidos se rechazan antes del primer ADB.

## Auxiliar ADB de la rama nueva

El controller usa reviewed_adb.py de este mismo directorio. Es una copia del auxiliar histórico con el único cambio de importar la guardia actual en main; el import del controller apunta a esa copia. El subprocess conserva GITHUB_REF real y recibe PYTHONPATH=lab/qa del workflow. Esto corrige el bloqueo de la guardia histórica observado en el ensayo ART antes de crear el AVD. URL, hash del archivo, cuatro miembros, extracción, no redirects, pins del ADB, destino propio y plazo de90s conservan su lógica original. El auxiliar histórico y el matrix lock permanecen intactos.
