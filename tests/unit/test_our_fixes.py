"""
test_our_fixes.py — Tests for every bug fixed in this session.
These directly verify the specific changes made so regressions are
caught immediately if any file is accidentally reverted.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── 1. Canonicalization fixes (database.py) ─────────────────────────────────

class TestCanonicalizationFixes:
    """Verify the two canonicalization bugs we fixed in _OUTLET_NAME_CANONICAL."""

    @pytest.fixture(autouse=True)
    def load_canon_map(self):
        with open(os.path.join(os.path.dirname(__file__), '..', '..', 'modules', 'database.py'), encoding='utf-8') as f:
            src = f.read()
        start = src.index('_OUTLET_NAME_CANONICAL: dict[str, str] = {')
        end   = src.index('\ndef canonicalize_outlet_name', start)
        dict_src = src[start:end].strip().replace(
            '_OUTLET_NAME_CANONICAL: dict[str, str] = ', '_OUTLET_NAME_CANONICAL = '
        )
        ns = {}
        exec(dict_src, ns)
        self.canon_map = ns['_OUTLET_NAME_CANONICAL']

    def _co(self, outlet):
        return self.canon_map.get(str(outlet).strip().lower(), str(outlet).strip())

    def test_centurion_lounge_bare_maps_to_t3(self):
        """BUG-001: 'Centurion Lounge' (bare) must map to T3, not T1."""
        assert self._co("Centurion Lounge") == "Centurion Lounge T3"

    def test_centurion_lounge_t1_explicit_maps_to_t1(self):
        """Explicit T1 suffix must still resolve to T1."""
        assert self._co("Centurion Lounge T1") == "Centurion Lounge T1"

    def test_centurion_lounge_t3_explicit_maps_to_t3(self):
        """Explicit T3 suffix must still resolve to T3."""
        assert self._co("Centurion Lounge T3") == "Centurion Lounge T3"

    def test_t1d_amex_lounge_maps_to_t1(self):
        """T1D new Amex Lounge (level 4) must map to T1."""
        assert self._co("T1D new Amex Lounge (level 4)") == "Centurion Lounge T1"

    def test_domestic_centurion_amex_t1_maps_to_t1(self):
        assert self._co("DomesticLounge- Centurion Amex T1") == "Centurion Lounge T1"

    def test_domestic_centurion_amex_t3_maps_to_t3(self):
        assert self._co("DomesticLounge- Centurion Amex T3") == "Centurion Lounge T3"

    def test_spa_domestic_maps_to_t3(self):
        """BUG-002: 'SPA Domestic' must map to T3, not T1."""
        assert self._co("SPA Domestic") == "Domestic Spa - T3"

    def test_spa_domestic_lowercase_maps_to_t3(self):
        assert self._co("spa domestic") == "Domestic Spa - T3"

    def test_t1d_spa_maps_to_t1(self):
        """T1D SPA must still map to T1."""
        assert self._co("T1D SPA") == "Domestic Spa - T1"

    def test_domestic_spa_t1_maps_to_t1(self):
        assert self._co("Domestic Spa- T1") == "Domestic Spa - T1"

    def test_domestic_spa_dpa10_t3_maps_to_t3(self):
        assert self._co("Domestic Spa- DPA10 T3") == "Domestic Spa - T3"

    def test_no_cross_group_collision_amex(self):
        """T1 and T3 Amex must never canonicalize to the same name."""
        t1 = self._co("Centurion Lounge T1")
        t3 = self._co("Centurion Lounge T3")
        assert t1 != t3

    def test_no_cross_group_collision_spa(self):
        """T1 and T3 Spa must never canonicalize to the same name."""
        t1 = self._co("Domestic Spa - T1")
        t3 = self._co("Domestic Spa - T3")
        assert t1 != t3


# ── 2. Display name fixes (outlet_groups.py) ────────────────────────────────

class TestDisplayNameFixes:
    """Verify display names for spa outlets after our outlet_groups.py fix."""

    def setup_method(self):
        from modules.outlet_groups import get_display_name
        self.gdn = get_display_name

    def test_spa_domestic_display_is_t3_dom(self):
        """BUG-003: 'SPA Domestic' display must be T3 Dom, not T1."""
        assert self.gdn("SPA Domestic", "Delhi") == "Encalm Spa (T3 Dom)"

    def test_dom_spa_display_is_t3_dom(self):
        """BUG-003: 'Dom Spa' display must be T3 Dom, not T1."""
        assert self.gdn("Dom Spa", "Delhi") == "Encalm Spa (T3 Dom)"

    def test_t1d_spa_display_is_t1_dom(self):
        """T1D SPA display must remain T1 Dom."""
        assert self.gdn("T1D SPA", "Delhi") == "Encalm Spa (T1 Dom)"

    def test_domestic_spa_t1_display_is_t1_dom(self):
        assert self.gdn("Domestic Spa - T1", "Delhi") == "Encalm Spa (T1 Dom)"

    def test_t3_int_spa_display(self):
        assert self.gdn("Spa - International", "Delhi") == "Encalm Spa (T3 INT)"

    def test_no_display_name_collision_between_t1_and_t3_spa(self):
        """T1 and T3 Dom spa must have different display names — or seen_display will suppress one."""
        t1_disp = self.gdn("T1D SPA", "Delhi")
        t3_disp = self.gdn("SPA Domestic", "Delhi")
        assert t1_disp != t3_disp


# ── 3. RL Delhi exclusion (outlet_groups.py) ────────────────────────────────

class TestRLDelhiExclusion:
    """BUG-004: RL Delhi must not appear in any Delhi group."""

    def setup_method(self):
        from modules.outlet_groups import DELHI_GROUPS
        self.groups = DELHI_GROUPS

    def test_reserved_lounge_not_in_la22_group(self):
        la22 = self.groups.get("T3 Arrivals LA22", [])
        assert "Reserved Lounge" not in la22

    def test_reserved_lounge_in_correct_group(self):
        # Reserved Lounge must be in its own group (not mixed into LA22 or any other group).
        # It is intentionally included under the "Reserved Lounge" group key to surface
        # it in the Lounges section of the EHPL table.
        assert "Reserved Lounge" in self.groups, \
            "Reserved Lounge must have its own group key in DELHI_GROUPS"
        # Must NOT appear as alias in any OTHER group
        for gk, outlets in self.groups.items():
            if gk == "Reserved Lounge":
                continue
            for o in outlets:
                assert "reserved lounge" not in o.lower(), \
                    f"Reserved Lounge alias found in wrong group '{gk}'"
        # RL Delhi group key should not exist
        for gk in self.groups:
            assert "RL Delhi" not in gk


# ── 4. T1 / T2 subtotals (outlet_groups.py) ─────────────────────────────────

class TestT1T2Subtotals:
    """Verify Total T1 and Total T2 subtotals exist and are arithmetically correct."""

    def setup_method(self):
        from modules.outlet_groups import DELHI_SUBTOTALS
        self.subtotal_map = {label: sources for label, sources in DELHI_SUBTOTALS}

    def test_total_t1_exists(self):
        assert "Total T1" in self.subtotal_map

    def test_total_t2_exists(self):
        assert "Total T2" in self.subtotal_map

    def test_total_t1_contains_correct_groups(self):
        t1 = set(self.subtotal_map["Total T1"])
        assert "T1D (Lounges)" in t1
        assert "Encalm Prive (T1)" in t1
        assert "Amex Lounge T1" in t1
        assert "T2 (Lounges)" not in t1

    def test_total_t2_contains_only_t2(self):
        t2 = self.subtotal_map["Total T2"]
        assert t2 == ["T2 (Lounges)"]

    def test_t1_plus_t2_equals_combined(self):
        """Total T1 + Total T2 must be exactly the same groups as Total(T1+T2)."""
        t1_groups = set(self.subtotal_map["Total T1"])
        t2_groups = set(self.subtotal_map["Total T2"])
        combined  = set(self.subtotal_map["Total(T1+T2)"])
        assert t1_groups | t2_groups == combined

    def test_total_t1_appears_before_t2_in_row_order(self):
        from modules.outlet_groups import DELHI_ROW_ORDER
        idx_t1 = DELHI_ROW_ORDER.index("Total T1")
        idx_t2 = DELHI_ROW_ORDER.index("Total T2")
        assert idx_t1 < idx_t2

    def test_t2_appears_before_total_t2_in_row_order(self):
        from modules.outlet_groups import DELHI_ROW_ORDER
        idx_t2_lounge  = DELHI_ROW_ORDER.index("T2 (Lounges)")
        idx_total_t2   = DELHI_ROW_ORDER.index("Total T2")
        assert idx_t2_lounge < idx_total_t2


# ── 5. TOTAL EHPL composition ────────────────────────────────────────────────

class TestTotalEhplComposition:
    """TOTAL EHPL must include all required component groups."""

    def setup_method(self):
        from modules.outlet_groups import DELHI_SUBTOTALS
        self.ehpl_groups = set(
            next(s[1] for s in DELHI_SUBTOTALS if s[0] == "TOTAL EHPL")
        )

    def test_ehpl_includes_all_spa(self):
        assert "Spa T3 INT" in self.ehpl_groups
        assert "Spa T3 Dom" in self.ehpl_groups
        assert "Spa T1"     in self.ehpl_groups

    def test_ehpl_includes_atithya(self):
        assert "Atithya (M&G)"    in self.ehpl_groups
        assert "Atithya (Porter)" in self.ehpl_groups
        assert "Atithya (Buggy)"  in self.ehpl_groups

    def test_ehpl_includes_arrivals(self):
        assert "T3 Arrivals LA22" in self.ehpl_groups
        assert "T3 Nap LA01"      in self.ehpl_groups
        assert "T3 Nap LA12"      in self.ehpl_groups

    def test_ehpl_includes_t1_t2_t3(self):
        assert "T1D (Lounges)"         in self.ehpl_groups
        assert "T2 (Lounges)"          in self.ehpl_groups
        assert "T3 Domestic DL02/3/4"  in self.ehpl_groups
        assert "T3 International"      in self.ehpl_groups

    def test_ehpl_excludes_rl_delhi(self):
        """RL Delhi must not be included in TOTAL EHPL."""
        for gk in self.ehpl_groups:
            assert "RL Delhi" not in gk
            assert "Reserved Lounge" not in gk


# ── 6. Session auth key preservation (session.py) ───────────────────────────

class TestClearSessionPreservesAuth:
    """BUG-005: clear_session() must never delete authentication keys."""

    def test_auth_keys_preserved_after_clear_session(self, monkeypatch):
        pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")
        import streamlit as st
        from unittest.mock import MagicMock, patch

        # Build a fake session_state with auth keys + workspace keys
        fake_state = {
            "_authenticated_user":   "testuser",
            "_session_token":        "abc123",
            "_session_created_at":   "2025-01-01",
            "_db_bootstrapped":      True,
            "active_analysis_date":  "2025-06-01",
            "compare_analysis_date": "2025-05-01",
            "_last_upload_results":  [],
        }

        mock_ss = MagicMock()
        mock_ss.get = lambda k, d=None: fake_state.get(k, d)
        mock_ss.keys = lambda: list(fake_state.keys())
        mock_ss.__contains__ = lambda self, k: k in fake_state
        mock_ss.__delitem__ = lambda self, k: fake_state.pop(k)

        with patch('streamlit.session_state', mock_ss):
            from modules import session
            session.clear_session()

        # Auth keys must still be present
        assert "_authenticated_user"  in fake_state, "Auth key was deleted!"
        assert "_session_token"       in fake_state, "Session token was deleted!"
        assert "_session_created_at"  in fake_state, "Session created_at was deleted!"
        assert "_db_bootstrapped"     in fake_state, "Bootstrap key was deleted!"

        # Workspace keys must be gone
        assert "active_analysis_date"  not in fake_state
        assert "compare_analysis_date" not in fake_state
        assert "_last_upload_results"  not in fake_state
