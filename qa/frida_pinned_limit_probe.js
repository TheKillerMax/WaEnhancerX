'use strict';

Java.perform(function () {
    const candidateClasses = ['X.1Ep', 'X.C26621Ep'];
    let installed = false;

    candidateClasses.forEach(function (className) {
        if (installed) return;
        try {
            const limitOwner = Java.use(className);
            const getter = limitOwner.A00.overload(className);
            getter.implementation = function (owner) {
                const original = getter.call(this, owner);
                console.log('[WAEX_PIN_PROBE] ' + className + '.A00 original=' + original + ' forced=60');
                return 60;
            };
            installed = true;
            console.log('[WAEX_PIN_PROBE] hooked ' + className + '.A00(' + className + ')');
        } catch (error) {
            console.log('[WAEX_PIN_PROBE] candidate failed ' + className + ': ' + error);
        }
    });

    if (!installed) {
        console.log('[WAEX_PIN_PROBE] no pinned-limit getter candidate was hookable');
    }
});
