from app.services.analysis import _is_relevant_pc_listing, _similarity
from app.services.relevance import component_type_from_query, query_variants


def test_build_and_accessory_filtered():
    assert not _is_relevant_pc_listing("RTX 4060", "PC GAMING MINI Intel Core I7 14700F + RAM 32GB", "gpu")
    assert not _is_relevant_pc_listing("RX 6600", "Fan kipas vga ASRock Challenger Pro OC Rx 6600 6650 6700 6750", "gpu")
    assert _is_relevant_pc_listing("RTX 3060", "MSI GeForce RTX 3060 VENTUS 2X 12G OC", "gpu")


def test_multi_gpu_title_filtered():
    # judul aksesori biasanya menyebut banyak chipset sekaligus
    assert not _is_relevant_pc_listing("RTX 3060", "Fan VGA MSI RTX 3060 3070 3080 3090 Rx 6800 xt gaming X trio", "gpu")


def test_similarity_threshold_semantics():
    # "RX 6600" vs judul build yang mention RX 6600 = 1.0, jadi threshold
    # >=0.75 saja tidak cukup tanpa filter accessory/multi-chipset
    assert _similarity("RX 6600", "PC Hackintosh Intel i7 13700F RX 6600") == 1.0


def test_component_query_expansion_is_bounded_and_model_safe():
    variants = query_variants("RTX 3060", max_variants=5)
    assert variants[0] == "RTX 3060"
    assert "VGA RTX 3060" in variants
    assert "RTX 3060 bekas" in variants
    assert all("3060" in variant for variant in variants)
    assert component_type_from_query("processor Ryzen 5 5600") == "cpu"
