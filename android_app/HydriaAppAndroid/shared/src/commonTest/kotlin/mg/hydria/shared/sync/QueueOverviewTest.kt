package mg.hydria.shared.sync

import kotlin.test.*

class QueueOverviewTest {
    @Test fun conflictsAreStableAndExcludedFromOrdinaryCounters() {
        val result = QueueOverviewRules.summarize(listOf(
            QueueItem("r","reading","",false),QueueItem("p","terrain_photo","error",false),
            QueueItem("c","reading","cOnFlIt de version",false),QueueItem("d","terrain_photo","",true),
            QueueItem("other","unknown","",false)))
        assertEquals(listOf("r","p","c","d","other"),result.items)
        assertEquals(listOf("c","d"),result.conflicts)
        assertEquals(listOf("r","p","other"),result.ordinary)
        assertEquals(1,result.readingCount)
        assertEquals(1,result.photoCount)
        assertFalse(QueueOverviewRules.isConflict(false," Conflit"))
    }
    @Test fun refusedReadingIsOnlyAReadingMarkedByTheServerAndNotAConflict() {
        assertTrue(QueueOverviewRules.isServerRefusal("reading",true,false,"La remarque est obligatoire si la consommation est égale à 0"))
        // Pas de marqueur : panne réseau ou ancienne erreur, rien à corriger côté saisie.
        assertFalse(QueueOverviewRules.isServerRefusal("reading",false,false,"Unable to resolve host"))
        // Sans erreur enregistrée, rien n'a été refusé.
        assertFalse(QueueOverviewRules.isServerRefusal("reading",true,false,""))
        // Un conflit garde son parcours « Corriger / Comparer ».
        assertFalse(QueueOverviewRules.isServerRefusal("reading",true,true,"Conflit de version"))
        assertFalse(QueueOverviewRules.isServerRefusal("reading",true,false,"Conflit de version"))
        // Seuls les relevés se corrigent dans l'écran de saisie.
        assertFalse(QueueOverviewRules.isServerRefusal("terrain_photo",true,false,"Refusé"))
        assertEquals("_sync_refused",QueueOverviewRules.REFUSED_KEY)
    }
    @Test fun refusalMarkerFollowsTheLastSendOutcome() {
        // Seul un HTTP 400 sur un relevé pose le marqueur.
        assertTrue(QueueOverviewRules.isRefusalResponse("reading",400))
        // Toute autre issue le retire : succès, conflit, panne serveur, réponse absente (coupure / timeout).
        assertFalse(QueueOverviewRules.isRefusalResponse("reading",200))
        assertFalse(QueueOverviewRules.isRefusalResponse("reading",409))
        assertFalse(QueueOverviewRules.isRefusalResponse("reading",500))
        assertFalse(QueueOverviewRules.isRefusalResponse("reading",503))
        assertFalse(QueueOverviewRules.isRefusalResponse("reading",0))
        // Les autres types n'ont pas de parcours « Corriger ».
        assertFalse(QueueOverviewRules.isRefusalResponse("terrain_photo",400))
        // Refus (400) puis panne passagère : le marqueur retiré, l'erreur affichée n'est plus un refus.
        val afterOutage = QueueOverviewRules.isRefusalResponse("reading",500)
        assertFalse(QueueOverviewRules.isServerRefusal("reading",afterOutage,false,"Erreur HTTP 500"))
        // Refus (400) à nouveau : le marqueur est reposé.
        val afterRefusal = QueueOverviewRules.isRefusalResponse("reading",400)
        assertTrue(QueueOverviewRules.isServerRefusal("reading",afterRefusal,false,"La remarque est obligatoire"))
    }
    @Test fun statusAndUnknownTypeFallbacksRemainExact() {
        assertEquals("Synchronisation à jour",QueueOverviewRules.status(0,true))
        assertEquals("Hors ligne · rien en attente",QueueOverviewRules.status(0,false))
        assertEquals("2 en attente · reprise possible maintenant",QueueOverviewRules.status(2,true))
        assertEquals("Hors ligne · 2 conservée(s) sur ce téléphone",QueueOverviewRules.status(2,false))
        assertEquals("custom",QueueOverviewRules.typeLabel("custom"))
        assertEquals("Photo Terrain",QueueOverviewRules.typeLabel("terrain_photo"))
    }
}
