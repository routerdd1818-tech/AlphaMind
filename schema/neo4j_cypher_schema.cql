// ==============================================================================
// AlphaMind AI — Polyglot Persistence Architecture
// Layer 2: Neo4j 5+ Supply Chain Knowledge Graph Schema
// Standards: Strict schema constraints, weighted directed edges, query optimization
// ==============================================================================

// ------------------------------------------------------------------------------
// 1. Constraints & Uniqueness Enforcements
// ------------------------------------------------------------------------------
CREATE CONSTRAINT c_company_symbol_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.symbol IS UNIQUE;

CREATE CONSTRAINT c_product_id_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT c_material_id_unique IF NOT EXISTS
FOR (m:Material) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT c_concept_tag_id_unique IF NOT EXISTS
FOR (t:ConceptTag) REQUIRE t.id IS UNIQUE;

// ------------------------------------------------------------------------------
// 2. Indexes for High-Frequency Graph Traversals (BFS / PageRank)
// ------------------------------------------------------------------------------
CREATE INDEX idx_company_market IF NOT EXISTS
FOR (c:Company) ON (c.market);

CREATE INDEX idx_company_industry IF NOT EXISTS
FOR (c:Company) ON (c.industry);

CREATE INDEX idx_supplies_to_revenue IF NOT EXISTS
FOR ()-[r:SUPPLIES_TO]-() ON (r.revenue_share);

CREATE INDEX idx_tagged_with_weight IF NOT EXISTS
FOR ()-[r:TAGGED_WITH]-() ON (r.weight);

// ------------------------------------------------------------------------------
// 3. Schema Structure & Edge Metadata Definitions
// ------------------------------------------------------------------------------
// Node Labels:
// (:Company { symbol: '2330.TW', name: '台積電', market: 'TWSE', market_cap: 26500000000000.0, industry: '半導體' })
// (:Product { id: 'PRD_COWOS_PACKAGING', name: 'CoWoS 先進封裝', category: 'PACKAGING_SERVICE' })
// (:Material { id: 'MAT_ABF_SUBSTRATE', name: 'ABF載板', chemical_type: 'SUBSTRATE' })
// (:ConceptTag { id: 'TAG_AI_SERVER', name: 'AI 伺服器', category: 'THEME' })

// Relationship Definitions:
// 1. SUPPLIES_TO (有向供貨關係):
//    (:Company)-[:SUPPLIES_TO {
//       revenue_share: 0.35,      // 該產品供貨佔供應商整體營收比例 (0.0 ~ 1.0)
//       confidence: 0.95,         // AI 萃取置信度
//       source_doc: '113年股東會年報 p.48',
//       verified_by_human: true,
//       updated_at: datetime()
//    }]->(:Company)

// 2. BUYS_FROM (採購客戶關係):
//    (:Company)-[:BUYS_FROM {
//       cost_share: 0.20,         // 採購額佔買方成本比重
//       confidence: 0.90
//    }]->(:Company)

// 3. COMPETES_WITH (同業競爭關係):
//    (:Company)-[:COMPETES_WITH {
//       overlap_degree: 0.85      // 產品與客戶重疊度
//    }]->(:Company)

// 4. PRODUCES (生產產品):
//    (:Company)-[:PRODUCES {
//       is_primary: true
//    }]->(:Product)

// 5. REQUIRES_MATERIAL (產品原料需求):
//    (:Product)-[:REQUIRES_MATERIAL {
//       is_critical: true
//    }]->(:Material)

// 6. TAGGED_WITH (概念族群關聯):
//    (:Company)-[:TAGGED_WITH {
//       weight: 0.80              // 題材純度權重
//    }]->(:ConceptTag)

// ------------------------------------------------------------------------------
// 4. Critical Query Templates (供應鏈傳導與落後補漲分析)
// ------------------------------------------------------------------------------

// Template A: 查詢特定龍頭公司（如 NVDA）的 1 至 3 階台股供應商，並計算累計權重
// MATCH path = (twSupplier:Company)-[r:SUPPLIES_TO*1..3]->(leader:Company {symbol: 'NVDA'})
// WHERE twSupplier.market IN ['TWSE', 'TPEx']
// WITH twSupplier, path, length(path) as tier,
//      reduce(w = 1.0, rel IN relationships(path) | w * rel.revenue_share) as cum_weight
// RETURN twSupplier.symbol as symbol,
//        twSupplier.name as name,
//        tier,
//        cum_weight,
//        [node IN nodes(path) | node.name] as chain_path
// ORDER BY tier ASC, cum_weight DESC;

// Template B: 概念股衝擊傳導（當關鍵物料斷鏈時，查找所有受波及之下游產品與組裝廠）
// MATCH (m:Material {id: $material_id})<-[:REQUIRES_MATERIAL]-(p:Product)<-[:PRODUCES]-(supplier:Company)
// MATCH (supplier)-[r:SUPPLIES_TO]->(customer:Company)
// RETURN m.name as material,
//        p.name as affected_product,
//        supplier.name as component_maker,
//        customer.name as affected_customer,
//        r.revenue_share as exposure
// ORDER BY r.revenue_share DESC;
