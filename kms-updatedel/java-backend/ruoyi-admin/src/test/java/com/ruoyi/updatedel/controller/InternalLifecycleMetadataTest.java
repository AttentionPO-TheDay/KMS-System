package com.ruoyi.updatedel.controller;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import com.ruoyi.updatedel.domain.Keymanage;
import com.ruoyi.updatedel.service.LifecycleService;

class InternalLifecycleMetadataTest {
    @Test void snapshotsExposeOnlyMetadataAndStillRequireInternalAuthorization() {
        LifecycleService service = mock(LifecycleService.class);
        InternalLifecycleController controller = new InternalLifecycleController(service, null, null, null, null, null, null, null, null);
        ReflectionTestUtils.setField(controller, "internalToken", "test-internal");
        Keymanage key = new Keymanage();
        key.setKeyId(1L); key.setVersion(2); key.setStatus("0");
        key.setUserName("acceptance_user"); key.setKeyDomain("acceptance");
        key.setKeyValue("NEVER_EXPOSE_MATERIAL");
        when(service.metadataByIds(Arrays.asList(1L, 2L))).thenReturn(Collections.singletonList(key));
        assertThrows(IllegalArgumentException.class, () -> controller.keyStatus(null, Arrays.asList(1L)));
        Map<String, Object> result = controller.keyStatus("test-internal", Arrays.asList(1L, 2L));
        List<Map<String, Object>> rows = (List<Map<String, Object>>) result.get("data");
        assertEquals(2, rows.size()); assertEquals(2, rows.get(0).get("version"));
        assertEquals("acceptance_user", rows.get(0).get("userName"));
        assertEquals("acceptance", rows.get(0).get("keyDomain"));
        assertEquals(false, rows.get(1).get("exists"));
        assertFalse(result.toString().contains("NEVER_EXPOSE"));
        assertFalse(rows.get(0).containsKey("keyValue"));
        verify(service).metadataByIds(Arrays.asList(1L, 2L));
        verify(service, never()).findById(anyLong());
    }
}
