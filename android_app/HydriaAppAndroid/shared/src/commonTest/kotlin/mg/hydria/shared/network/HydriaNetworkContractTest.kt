package mg.hydria.shared.network

import io.ktor.client.HttpClient
import io.ktor.client.engine.mock.MockEngine
import io.ktor.client.engine.mock.respond
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.request.HttpRequestData
import io.ktor.client.request.forms.FormDataContent
import io.ktor.http.*
import io.ktor.http.content.OutgoingContent
import io.ktor.serialization.kotlinx.json.json
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import kotlin.test.*
import mg.hydria.shared.plannings.HydriaPlanningsClient
import mg.hydria.shared.repairs.HydriaRepairsClient
import mg.hydria.shared.readings.HydriaReadingsClient
import mg.hydria.shared.interventions.HydriaInterventionsClient
import mg.hydria.shared.billing.HydriaVolumeClient
import mg.hydria.shared.navigation.HydriaNavigationClient
import mg.hydria.shared.terrain.HydriaTerrainClient
import mg.hydria.shared.search.HydriaSearchClient
import mg.hydria.shared.calculator.HydriaSalaryConfigClient

class HydriaNetworkContractTest {
    private fun jsonPayload(text: String) = HydriaHttpClient.json.parseToJsonElement(text).jsonObject
    private fun withClient(block: suspend (HttpClient, MutableList<HttpRequestData>) -> Unit) = runBlocking {
        val requests = mutableListOf<HttpRequestData>()
        val engine = MockEngine { request ->
            requests.add(request)
            respond("{\"success\":true}", HttpStatusCode.OK, headersOf(HttpHeaders.ContentType, "application/json"))
        }
        val client = HttpClient(engine) {
            install(ContentNegotiation) { json(HydriaHttpClient.json) }
            defaultRequest { url(HydriaHttpClient.BASE_URL) }
        }
        try { block(client, requests) } finally { client.close() }
        assertTrue(requests.isNotEmpty())
        requests.forEach { assertEquals("Token test-token", it.headers[HttpHeaders.Authorization]) }
    }
    private fun HttpRequestData.form() = (body as FormDataContent).formData
    private fun HttpRequestData.jsonBody() = jsonPayload((body as OutgoingContent.ByteArrayContent).bytes().decodeToString())

    @Test fun planningAndRepairKeepFieldAllowlistAndPostPaths() = withClient { client, requests ->
        val payload = jsonPayload("""{"id":"12","employe_id":"4","date":"2026-09-07","remarque":"école & eau","_sync_conflict":{},"ignored":"no"}""")
        HydriaPlanningsClient.savePlanning(client, "test-token", payload)
        HydriaPlanningsClient.saveRepair(client, "test-token", payload)
        HydriaRepairsClient.finishRepair(client, "test-token", "12")
        assertEquals(listOf("/plannings/api/mobile/planning/enregistrer/", "/plannings/api/mobile/reparation/enregistrer/", "/plannings/reparations/api/12/marquer-terminee/"), requests.map { it.url.encodedPath })
        requests.forEach { assertEquals(HttpMethod.Post, it.method) }
        assertEquals(setOf("id", "employe_id", "date", "remarque"), requests[0].form().names())
        assertEquals("école & eau", requests[0].form()["remarque"])
        assertTrue(requests[2].form().isEmpty())
    }

    @Test fun readingsPreserveDefaultsOptionalFieldsAndSocialCards() = withClient { client, requests ->
        HydriaReadingsClient.saveReading(client, "test-token", jsonPayload("""{"point_eau_id":"9","date_releve":"2026-09-07","nouvel_index":123,"local_uuid":"reading-1","terrain_latitude":-18.4,"point_photo_data":null,"cartes_sociales":[{"id":1}]}"""))
        val request = requests.single()
        assertEquals("/facturation/api/save-releve-terrain/", request.url.encodedPath)
        val form = request.form()
        assertEquals("123.0", form["nouvel_index"])
        assertEquals("0.0", form["volume_non_facture"])
        assertEquals("", form["remarque"])
        assertEquals("[{\"id\":1}]", form["cartes_sociales"])
        assertEquals("reading-1", form["local_uuid"])
        assertEquals("-18.4", form["terrain_latitude"])
        assertNull(form["point_photo_data"])
    }

    @Test fun invoicesRemainAGetInReadings() = withClient { client, requests ->
        HydriaPlanningsClient.pointInvoices(client, "test-token", "9")
        assertEquals(HttpMethod.Get, requests.single().method)
        assertEquals("/plannings/api/mobile/point-eau/9/factures/", requests.single().url.encodedPath)
    }

    @Test fun interventionsPreservePaginationFormsAndJson() = withClient { client, requests ->
        HydriaInterventionsClient.list(client, "test-token", 3, true, "en cours", "created")
        HydriaInterventionsClient.postpone(client, "test-token", "12", "2026-09-10")
        HydriaInterventionsClient.delete(client, "test-token", "12")
        HydriaInterventionsClient.options(client, "test-token", "5")
        val payload = jsonPayload("""{"remarque":"école & eau","participants":[1,2],"actif":true}""")
        HydriaInterventionsClient.update(client, "test-token", "5", "12", payload)
        val query = requests[0].url.parameters
        assertEquals("3", query["page"]); assertEquals("20", query["page_size"])
        assertEquals("1", query["all_bases"]); assertEquals("en cours", query["status"])
        assertEquals("2026-09-10", requests[1].form()["date"])
        assertTrue(requests[2].form().isEmpty())
        assertEquals("/recherche/ouvrages/5/interventions/options/", requests[3].url.encodedPath)
        assertEquals("/recherche/ouvrages/5/interventions/12/modifier/", requests[4].url.encodedPath)
        assertEquals(payload, requests[4].jsonBody())
    }

    @Test fun volumeStripsOnlyTopLevelSyncMetadataAndKeepsIdentity() = withClient { client, requests ->
        HydriaVolumeClient.bootstrap(client, "test-token", "5", "2026-09")
        val payload = jsonPayload("""{"local_uuid":"volume-1","account_key":"account","action":"valider","factures":[{"id":"8","version":"v1"}],"_sync_conflict":{}}""")
        HydriaVolumeClient.syncOperation(client, "test-token", payload)
        assertEquals("5", requests[0].url.parameters["ouvrage_id"])
        assertEquals("2026-09", requests[0].url.parameters["mois"])
        val sent = requests[1].jsonBody()
        assertEquals(payload["factures"], sent["factures"])
        assertEquals(payload["local_uuid"], sent["local_uuid"])
        assertEquals(payload["account_key"], sent["account_key"])
        assertFalse(sent.containsKey("_sync_conflict"))
        assertTrue(payload.containsKey("_sync_conflict"))
    }

    @Test fun navigationCursorsArchiveAndPhotoKeepTheirContracts() = withClient { client, requests ->
        HydriaNavigationClient.config(client, "test-token")
        HydriaNavigationClient.entities(client, "test-token", "a+b/c=", "1,2,3,4", 250)
        HydriaNavigationClient.savePosition(client, "test-token", jsonPayload("""{"local_uuid":"geo-1","latitude":-18.4,"_sync_conflict":{}}"""))
        HydriaNavigationClient.saveLandmark(client, "test-token", jsonPayload("""{"id":"7","operation_type":"landmark_archive"}"""))
        HydriaNavigationClient.savePhoto(client, "test-token", jsonPayload("""{"entity_id":"7","photo_data":"ab+c/==","local_uuid":"photo-1"}"""))
        assertEquals("a+b/c=", requests[1].url.parameters["cursor"])
        assertEquals("1,2,3,4", requests[1].url.parameters["bbox"])
        assertEquals("250", requests[1].url.parameters["limit"])
        assertNull(requests[2].form()["_sync_conflict"])
        assertEquals("geo-1", requests[2].form()["local_uuid"])
        assertEquals("/navigation-terrain/api/mobile/reperes/7/archive/", requests[3].url.encodedPath)
        assertEquals("/navigation-terrain/api/mobile/reperes/7/photos/", requests[4].url.encodedPath)
        assertEquals("ab+c/==", requests[4].form()["photo_data"])
    }

    @Test fun terrainStillUsesConditionalSnapshotAndPhotoForm() = withClient { client, requests ->
        HydriaTerrainClient.prepareTour(client, "test-token", "v1+&")
        HydriaTerrainClient.prepareTour(client, "test-token", " ")
        HydriaTerrainClient.saveItem(client, "test-token", jsonPayload("""{"operation_type":"photo_point","point_id":"9","photo_data":"ab+c/==","_sync_conflict":{}}"""))
        assertEquals("14", requests[0].url.parameters["horizon_jours"])
        assertEquals("v1+&", requests[0].url.parameters["snapshot_version"])
        assertNull(requests[1].url.parameters["snapshot_version"])
        assertEquals("ab+c/==", requests[2].form()["photo_data"])
        assertNull(requests[2].form()["_sync_conflict"])
        // Octets reellement envoyes : Django decode "+" brut en espace, ce qui
        // casse le base64 des photos ("Photo invalide"). Le "+" doit partir en %2B.
        val wire = (requests[2].body as OutgoingContent.ByteArrayContent).bytes().decodeToString()
        assertEquals("ab+c/==", parseQueryString(wire, decode = true)["photo_data"], "corps envoye : $wire")
    }

    @Test fun responseErrorsNeverBecomeSuccessfulWrites() {
        assertFalse(decodeHydriaResponse(200, "<html>login</html>").successful)
        assertFalse(decodeHydriaResponse(200, "broken json").successful)
        assertFalse(decodeHydriaResponse(200, "[]").successful)
        assertFalse(decodeHydriaResponse(200, "{\"success\":false}").successful)
        assertFalse(decodeHydriaResponse(409, "{\"error\":\"conflit\"}").successful)
        assertEquals("conflit", decodeHydriaResponse(409, "{\"error\":\"conflit\"}").error)
        assertFalse(decodeHydriaResponse(503, "").successful)
        assertTrue(decodeHydriaResponse(204, "").successful)
    }

    @Test fun searchPreservesFiltersAndEncodesDynamicPaths() = withClient { client, requests ->
        HydriaSearchClient.search(client, "test-token", "école & eau", setOf("point", "ouvrage"), 2)
        HydriaSearchClient.people(client, "test-token", "nom +", "abonne", "actif", 3)
        HydriaSearchClient.works(client, "test-token", "source", 4, "r", "d", "c", "e")
        HydriaSearchClient.workFilters(client, "test-token")
        HydriaSearchClient.searchDetail(client, "test-token", "point", "a/b +é")
        HydriaSearchClient.personDetail(client, "test-token", "abonne", "9")
        assertEquals("école & eau", requests[0].url.parameters["q"])
        assertEquals("point,ouvrage", requests[0].url.parameters["types"])
        assertEquals("2", requests[0].url.parameters["page"])
        assertEquals("actif", requests[1].url.parameters["statut"])
        assertEquals("nom +", requests[1].url.parameters["search"])
        assertEquals("e", requests[2].url.parameters["employee"])
        assertEquals("c", requests[2].url.parameters["commune"])
        assertEquals("d", requests[2].url.parameters["district"])
        assertEquals("r", requests[2].url.parameters["region"])
        assertEquals("/recherche/api/mobile/ouvrages/filtres/", requests[3].url.encodedPath)
        assertEquals("/recherche/api/mobile/details/point/a%2Fb+%2B%C3%A9/", requests[4].url.encodedPath)
        assertEquals("/recherche/api/mobile/personnes/abonne/9/", requests[5].url.encodedPath)
    }

    @Test fun calculatorKeepsConditionalChecksum() = withClient { client, requests ->
        HydriaSalaryConfigClient.fetch(client, "test-token", "a+b/c=")
        HydriaSalaryConfigClient.fetch(client, "test-token", " ")
        assertEquals("a+b/c=", requests[0].url.parameters["checksum"])
        assertNull(requests[1].url.parameters["checksum"])
    }

    @Test fun interventionIdsKeepLegacyPathEncoding() = withClient { client, requests ->
        HydriaInterventionsClient.postpone(client, "test-token", "a/b +é", "2026-09-10")
        assertEquals("/recherche/api/mobile/interventions/a%2Fb+%2B%C3%A9/reporter/", requests.single().url.encodedPath)
    }

    @Test fun transportExceptionsReachTheSessionRouter() = runBlocking {
        val engine = MockEngine { error("transport interrupted") }
        val client = HttpClient(engine)
        try {
            val response = runCatching { HydriaNavigationClient.config(client, "test-token") }
            assertTrue(response.isFailure)
        } finally { client.close() }
    }
}
