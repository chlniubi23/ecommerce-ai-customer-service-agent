USE ai_agent_commerce_demo;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE workflow_runtime_records;
TRUNCATE TABLE agent_audit_logs;
TRUNCATE TABLE supervisor_escalations;
TRUNCATE TABLE human_agent_status;
TRUNCATE TABLE complaint_escalations;
TRUNCATE TABLE complaint_process_records;
TRUNCATE TABLE complaints;
TRUNCATE TABLE refunds;
TRUNCATE TABLE logistics_tracking_events;
TRUNCATE TABLE logistics_shipments;
TRUNCATE TABLE carriers;
TRUNCATE TABLE order_items;
TRUNCATE TABLE orders;
TRUNCATE TABLE inventory_history;
TRUNCATE TABLE inventory;
TRUNCATE TABLE product_collection_items;
TRUNCATE TABLE product_images;
TRUNCATE TABLE products;
TRUNCATE TABLE product_collections;
TRUNCATE TABLE categories;
TRUNCATE TABLE brands;

SET FOREIGN_KEY_CHECKS = 1;

SET @demo_user_id := (SELECT user_id FROM users ORDER BY created_at DESC LIMIT 1);
SET @demo_address_id := (
  SELECT address_id
  FROM user_addresses
  WHERE user_id = @demo_user_id
  ORDER BY is_default DESC, created_at DESC
  LIMIT 1
);

INSERT INTO brands (brand_id, brand_name, description, brand_status, tags) VALUES
('BRD_DOU001', '抖选数码', '适合直播电商演示的手机、耳机与智能硬件品牌', '正常', JSON_ARRAY('数码','热卖','AI推荐')),
('BRD_DOU002', '轻居生活', '覆盖居家、收纳和小家电的生活方式品牌', '正常', JSON_ARRAY('居家','品质','复购')),
('BRD_DOU003', '悦己美研', '护肤、彩妆和个护类演示品牌', '正常', JSON_ARRAY('美妆','礼盒','活动'));

INSERT INTO categories (category_id, parent_id, category_name, category_level, category_path, category_status, sort_order) VALUES
('CAT_DOU_DIGITAL', NULL, '数码家电', 1, '数码家电', '正常', 1),
('CAT_DOU_PHONE', 'CAT_DOU_DIGITAL', '手机数码', 2, '数码家电/手机数码', '正常', 1),
('CAT_DOU_AUDIO', 'CAT_DOU_DIGITAL', '影音耳机', 2, '数码家电/影音耳机', '正常', 2),
('CAT_DOU_HOME', NULL, '居家生活', 1, '居家生活', '正常', 2),
('CAT_DOU_BEAUTY', NULL, '美妆个护', 1, '美妆个护', '正常', 3);

INSERT INTO product_collections (collection_id, collection_name, description, collection_status) VALUES
('COL_DOU_HOT', '低价秒杀', '用于首页秒杀和双列商品流展示', '正常'),
('COL_DOU_AI', 'AI导购推荐', '用于演示 Product Agent 推荐能力', '正常');

INSERT INTO products (
  product_id, sku_id, brand_id, category_id, product_name, description,
  price, currency, product_status, version, tags, attributes, published_at, created_at
) VALUES
('PROD_DEMO_001', 'SKU_DEMO_001', 'BRD_DOU001', 'CAT_DOU_PHONE', '星耀 X1 Pro 5G 手机',
 '主打影像、长续航和直播间秒杀价，适合演示商品咨询、参数问答和下单。',
 3299.00, 'CNY', '上架', 1, JSON_ARRAY('热卖','百亿补贴','手机'),
 JSON_OBJECT('颜色','星河银','内存','12GB+256GB','卖点','5000mAh 长续航，OIS 防抖影像','售后','7天无理由，1年质保'),
 NOW(), DATE_SUB(NOW(), INTERVAL 8 DAY)),
('PROD_DEMO_002', 'SKU_DEMO_002', 'BRD_DOU001', 'CAT_DOU_AUDIO', '云感降噪 Pro 耳机',
 '主动降噪、通勤佩戴舒适，适合演示库存查询、商品对比和推荐。',
 599.00, 'CNY', '上架', 1, JSON_ARRAY('热卖','降噪','通勤'),
 JSON_OBJECT('颜色','曜石黑','续航','36小时','降噪','混合主动降噪','适用','通勤/运动/会议'),
 NOW(), DATE_SUB(NOW(), INTERVAL 7 DAY)),
('PROD_DEMO_003', 'SKU_DEMO_003', 'BRD_DOU002', 'CAT_DOU_HOME', '轻居智能扫地机器人',
 '可联动 App、自动回充，适合演示高客单价商品咨询和物流查询。',
 1899.00, 'CNY', '上架', 1, JSON_ARRAY('家电','智能家居','新品'),
 JSON_OBJECT('清洁模式','扫拖一体','续航','150分钟','水箱','电控水箱','质保','整机1年'),
 NOW(), DATE_SUB(NOW(), INTERVAL 6 DAY)),
('PROD_DEMO_004', 'SKU_DEMO_004', 'BRD_DOU003', 'CAT_DOU_BEAUTY', '悦己修护水乳礼盒',
 '适合演示活动咨询、退款售后和礼盒推荐。',
 268.00, 'CNY', '上架', 1, JSON_ARRAY('美妆','礼盒','复购'),
 JSON_OBJECT('肤质','干皮/混干','规格','水150ml+乳120ml','功效','保湿修护','保质期','36个月'),
 NOW(), DATE_SUB(NOW(), INTERVAL 5 DAY)),
('PROD_DEMO_005', 'SKU_DEMO_005', 'BRD_DOU001', 'CAT_DOU_AUDIO', '直播麦克风套装',
 '适合内容创作者入门直播，库存紧张，用于演示缺货/低库存提醒。',
 399.00, 'CNY', '上架', 1, JSON_ARRAY('直播','低库存','配件'),
 JSON_OBJECT('接口','USB-C','适用','直播/会议/录音','套装','麦克风+支架+防喷罩','库存提示','库存紧张'),
 NOW(), DATE_SUB(NOW(), INTERVAL 4 DAY)),
('PROD_DEMO_006', 'SKU_DEMO_006', 'BRD_DOU002', 'CAT_DOU_HOME', '折叠收纳推车',
 '预售商品，用于演示预售状态、发货时效和通用政策咨询。',
 129.00, 'CNY', '预售', 1, JSON_ARRAY('预售','居家','收纳'),
 JSON_OBJECT('材质','碳钢','层数','三层','预计发货','7日内','颜色','奶油白'),
 NOW(), DATE_SUB(NOW(), INTERVAL 3 DAY));

INSERT INTO product_images (image_id, product_id, image_url, alt_text, is_primary, sort_order) VALUES
('IMG_DEMO_001', 'PROD_DEMO_001', '/products/smartphone.jpg', 'smartphone real product image', 1, 1),
('IMG_DEMO_002', 'PROD_DEMO_002', '/products/earbuds.jpg', 'wireless earbuds real product image', 1, 1),
('IMG_DEMO_003', 'PROD_DEMO_003', '/products/robot-vacuum.jpg', 'robot vacuum real product image', 1, 1),
('IMG_DEMO_004', 'PROD_DEMO_004', '/products/skincare-set.jpg', 'skincare set real product image', 1, 1),
('IMG_DEMO_005', 'PROD_DEMO_005', '/products/stream-microphone.jpg', 'streaming microphone real product image', 1, 1),
('IMG_DEMO_006', 'PROD_DEMO_006', '/products/storage-cart.jpg', 'storage cart real product image', 1, 1);

INSERT INTO product_collection_items (collection_id, product_id, sort_order) VALUES
('COL_DOU_HOT', 'PROD_DEMO_001', 1),
('COL_DOU_HOT', 'PROD_DEMO_002', 2),
('COL_DOU_HOT', 'PROD_DEMO_004', 3),
('COL_DOU_HOT', 'PROD_DEMO_005', 4),
('COL_DOU_AI', 'PROD_DEMO_003', 1),
('COL_DOU_AI', 'PROD_DEMO_006', 2);

INSERT INTO inventory (
  inventory_id, product_id, sku_id, quantity, available_quantity,
  reserved_quantity, safety_stock, inventory_status
) VALUES
('INV_DEMO_001', 'PROD_DEMO_001', 'SKU_DEMO_001', 120, 98, 22, 20, '有货'),
('INV_DEMO_002', 'PROD_DEMO_002', 'SKU_DEMO_002', 80, 63, 17, 15, '有货'),
('INV_DEMO_003', 'PROD_DEMO_003', 'SKU_DEMO_003', 28, 19, 9, 8, '有货'),
('INV_DEMO_004', 'PROD_DEMO_004', 'SKU_DEMO_004', 160, 143, 17, 30, '有货'),
('INV_DEMO_005', 'PROD_DEMO_005', 'SKU_DEMO_005', 12, 5, 7, 10, '库存紧张'),
('INV_DEMO_006', 'PROD_DEMO_006', 'SKU_DEMO_006', 0, 0, 0, 10, '预售');

INSERT INTO inventory_history (history_id, sku_id, change_type, quantity_delta, quantity_after, reason) VALUES
('IH_DEMO_001', 'SKU_DEMO_001', '入库', 120, 120, '演示数据初始化'),
('IH_DEMO_002', 'SKU_DEMO_005', '预留', -7, 5, '直播间订单预留库存');

INSERT INTO carriers (carrier_id, carrier_name, service_phone, carrier_status) VALUES
('CAR001', '顺丰速运', '95338', '正常'),
('CAR002', '京东物流', '950616', '正常');

-- 7 个订单覆盖清晰的状态谱系。关键设计：ORD_DEMO_004 / 005 是"已签收、
-- 可退货/可投诉但尚未创建退款或投诉记录"的订单，专门留给 Agent 现场执行——
-- 用户说"退款/投诉"后，助手真的写入一条新记录，体现"帮你做"而非只读数据。
INSERT INTO orders (
  order_id, user_id, shipping_address_id, order_status, payment_status,
  shipping_status, receipt_status, total_amount, currency, created_at, paid_at, completed_at
) VALUES
-- 运输中 → 物流查询演示
('ORD_DEMO_001', @demo_user_id, @demo_address_id, '已发货', '已支付', '运输中', '未收货', 3299.00, 'CNY', DATE_SUB(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 2 DAY), NULL),
-- 售后中（已有退款单）→ 跟进退款演示
('ORD_DEMO_002', @demo_user_id, @demo_address_id, '售后中', '已支付', '已签收', '已收货', 599.00, 'CNY', DATE_SUB(NOW(), INTERVAL 9 DAY), DATE_SUB(NOW(), INTERVAL 9 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY)),
-- 配送异常（已有投诉升级）→ 跟进投诉演示
('ORD_DEMO_003', @demo_user_id, @demo_address_id, '异常', '已支付', '配送异常', '未收货', 1899.00, 'CNY', DATE_SUB(NOW(), INTERVAL 4 DAY), DATE_SUB(NOW(), INTERVAL 4 DAY), NULL),
-- ⭐ 已签收、可退货、尚未退款 → 现场发起退款演示（Agent 写入新退款单）
('ORD_DEMO_004', @demo_user_id, @demo_address_id, '已完成', '已支付', '已签收', '已收货', 268.00, 'CNY', DATE_SUB(NOW(), INTERVAL 6 DAY), DATE_SUB(NOW(), INTERVAL 6 DAY), DATE_SUB(NOW(), INTERVAL 3 DAY)),
-- ⭐ 已签收、有质量问题、尚未投诉 → 现场创建投诉演示（Agent 写入新工单）
('ORD_DEMO_005', @demo_user_id, @demo_address_id, '已完成', '已支付', '已签收', '已收货', 399.00, 'CNY', DATE_SUB(NOW(), INTERVAL 7 DAY), DATE_SUB(NOW(), INTERVAL 7 DAY), DATE_SUB(NOW(), INTERVAL 4 DAY)),
-- 已完成（正常）→ 订单复盘/个性化推荐的历史依据
('ORD_DEMO_006', @demo_user_id, @demo_address_id, '已完成', '已支付', '已签收', '已收货', 1899.00, 'CNY', DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 20 DAY), DATE_SUB(NOW(), INTERVAL 16 DAY)),
-- 待支付 → 订单待确认演示
('ORD_DEMO_007', @demo_user_id, @demo_address_id, '待支付', '未支付', '未发货', '未收货', 599.00, 'CNY', DATE_SUB(NOW(), INTERVAL 3 HOUR), NULL, NULL);

INSERT INTO order_items (
  order_item_id, order_id, product_id, sku_id, product_name,
  quantity, unit_price, line_amount
) VALUES
('OI_DEMO_001', 'ORD_DEMO_001', 'PROD_DEMO_001', 'SKU_DEMO_001', '星耀 X1 Pro 5G 手机', 1, 3299.00, 3299.00),
('OI_DEMO_002', 'ORD_DEMO_002', 'PROD_DEMO_002', 'SKU_DEMO_002', '云感降噪 Pro 耳机', 1, 599.00, 599.00),
('OI_DEMO_003', 'ORD_DEMO_003', 'PROD_DEMO_003', 'SKU_DEMO_003', '轻居智能扫地机器人', 1, 1899.00, 1899.00),
('OI_DEMO_004', 'ORD_DEMO_004', 'PROD_DEMO_004', 'SKU_DEMO_004', '悦己修护水乳礼盒', 1, 268.00, 268.00),
('OI_DEMO_005', 'ORD_DEMO_005', 'PROD_DEMO_005', 'SKU_DEMO_005', '直播麦克风套装', 1, 399.00, 399.00),
('OI_DEMO_006', 'ORD_DEMO_006', 'PROD_DEMO_003', 'SKU_DEMO_003', '轻居智能扫地机器人', 1, 1899.00, 1899.00),
('OI_DEMO_007', 'ORD_DEMO_007', 'PROD_DEMO_002', 'SKU_DEMO_002', '云感降噪 Pro 耳机', 1, 599.00, 599.00);

INSERT INTO logistics_shipments (
  shipment_id, order_id, carrier_id, tracking_no, current_status,
  current_location, estimated_delivery_at, shipped_at, delivered_at
) VALUES
('SHP_DEMO_001', 'ORD_DEMO_001', 'CAR001', 'SFDEMO2026061601', '运输中', '广州转运中心', DATE_ADD(NOW(), INTERVAL 1 DAY), DATE_SUB(NOW(), INTERVAL 1 DAY), NULL),
('SHP_DEMO_002', 'ORD_DEMO_002', 'CAR001', 'SFDEMO2026060902', '已签收', '上海市浦东新区', DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_SUB(NOW(), INTERVAL 8 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY)),
('SHP_DEMO_003', 'ORD_DEMO_003', 'CAR002', 'JDDEMO2026061203', '配送异常', '杭州分拨中心', DATE_ADD(NOW(), INTERVAL 2 DAY), DATE_SUB(NOW(), INTERVAL 3 DAY), NULL),
('SHP_DEMO_004', 'ORD_DEMO_004', 'CAR001', 'SFDEMO2026061004', '已签收', '北京市朝阳区', DATE_SUB(NOW(), INTERVAL 3 DAY), DATE_SUB(NOW(), INTERVAL 5 DAY), DATE_SUB(NOW(), INTERVAL 3 DAY)),
('SHP_DEMO_005', 'ORD_DEMO_005', 'CAR002', 'JDDEMO2026060905', '已签收', '北京市朝阳区', DATE_SUB(NOW(), INTERVAL 4 DAY), DATE_SUB(NOW(), INTERVAL 6 DAY), DATE_SUB(NOW(), INTERVAL 4 DAY)),
('SHP_DEMO_006', 'ORD_DEMO_006', 'CAR001', 'SFDEMO2026052706', '已签收', '北京市朝阳区', DATE_SUB(NOW(), INTERVAL 16 DAY), DATE_SUB(NOW(), INTERVAL 19 DAY), DATE_SUB(NOW(), INTERVAL 16 DAY));

INSERT INTO logistics_tracking_events (event_id, shipment_id, event_time, location, status, description) VALUES
('LTE_DEMO_001A', 'SHP_DEMO_001', DATE_SUB(NOW(), INTERVAL 42 HOUR), '深圳仓', '已揽收', '包裹已由顺丰揽收'),
('LTE_DEMO_001B', 'SHP_DEMO_001', DATE_SUB(NOW(), INTERVAL 20 HOUR), '广州转运中心', '运输中', '包裹正在发往目的地城市'),
('LTE_DEMO_002A', 'SHP_DEMO_002', DATE_SUB(NOW(), INTERVAL 8 DAY), '商家仓', '已揽收', '包裹已发出'),
('LTE_DEMO_002B', 'SHP_DEMO_002', DATE_SUB(NOW(), INTERVAL 5 DAY), '上海市浦东新区', '已签收', '本人已签收'),
('LTE_DEMO_003A', 'SHP_DEMO_003', DATE_SUB(NOW(), INTERVAL 3 DAY), '商家仓', '已揽收', '包裹已发出'),
('LTE_DEMO_003B', 'SHP_DEMO_003', DATE_SUB(NOW(), INTERVAL 12 HOUR), '杭州分拨中心', '配送异常', '外包装破损，已进入异常件处理'),
('LTE_DEMO_004A', 'SHP_DEMO_004', DATE_SUB(NOW(), INTERVAL 5 DAY), '商家仓', '已揽收', '包裹已发出'),
('LTE_DEMO_004B', 'SHP_DEMO_004', DATE_SUB(NOW(), INTERVAL 3 DAY), '北京市朝阳区', '已签收', '本人已签收'),
('LTE_DEMO_005A', 'SHP_DEMO_005', DATE_SUB(NOW(), INTERVAL 6 DAY), '商家仓', '已揽收', '包裹已发出'),
('LTE_DEMO_005B', 'SHP_DEMO_005', DATE_SUB(NOW(), INTERVAL 4 DAY), '北京市朝阳区', '已签收', '本人已签收'),
('LTE_DEMO_006A', 'SHP_DEMO_006', DATE_SUB(NOW(), INTERVAL 19 DAY), '商家仓', '已揽收', '包裹已发出'),
('LTE_DEMO_006B', 'SHP_DEMO_006', DATE_SUB(NOW(), INTERVAL 16 DAY), '北京市朝阳区', '已签收', '本人已签收');

-- 只预置 1 条退款（用于"跟进退款进度"演示）。ORD_DEMO_004 故意不建退款，
-- 留给 Agent 现场创建，展示"帮你把退款办了"。
INSERT INTO refunds (
  refund_id, order_id, user_id, refund_reason, refund_amount,
  audit_status, refund_status, created_at, updated_at
) VALUES
('REF_DEMO_001', 'ORD_DEMO_002', @demo_user_id, '耳机佩戴不适，申请七天无理由退货退款', 599.00, '审核中', '处理中', DATE_SUB(NOW(), INTERVAL 1 DAY), DATE_SUB(NOW(), INTERVAL 6 HOUR));

-- 只预置 1 条投诉（用于"跟进投诉进度"演示）。ORD_DEMO_005 故意不建投诉，
-- 留给 Agent 现场创建，展示"帮你把投诉工单提交了"。
INSERT INTO complaints (
  complaint_id, ticket_id, user_id, order_id, complaint_type, content,
  complaint_status, priority, created_at, updated_at, closed_at
) VALUES
('CMP_DEMO_001', 'TKT_DEMO_001', @demo_user_id, 'ORD_DEMO_003', '物流问题', '扫地机器人订单配送异常，外包装破损，希望尽快补发或赔付。', '已升级', '紧急', DATE_SUB(NOW(), INTERVAL 10 HOUR), DATE_SUB(NOW(), INTERVAL 2 HOUR), NULL);

INSERT INTO complaint_process_records (record_id, complaint_id, handler, action, note, created_at) VALUES
('CPR_DEMO_001', 'CMP_DEMO_001', 'ComplaintAgent', '已受理', '识别为物流异常且高客单价订单，进入投诉流程。', DATE_SUB(NOW(), INTERVAL 9 HOUR)),
('CPR_DEMO_002', 'CMP_DEMO_001', 'SupervisorAgent', '已升级', '满足主管介入条件：配送异常 + 用户要求赔付。', DATE_SUB(NOW(), INTERVAL 2 HOUR));

INSERT INTO complaint_escalations (
  escalation_id, complaint_id, escalation_reason, escalated_to,
  current_owner, supervisor_result, escalation_status, created_at, resolved_at
) VALUES
('CES_DEMO_001', 'CMP_DEMO_001', '配送异常涉及补发/赔付，需要主管审批', 'SupervisorAgent', 'SupervisorAgent', '建议优先补发，如用户拒收则发放 80 元关怀券。', '处理中', DATE_SUB(NOW(), INTERVAL 2 HOUR), NULL);

INSERT INTO supervisor_escalations (
  supervisor_escalation_id, source_agent, workflow_id, related_complaint_id,
  escalation_reason, current_owner, supervisor_result, escalation_status
) VALUES
('SUP_DEMO_001', 'ComplaintAgent', 'WF_DEMO_COMPLAINT_001', 'CMP_DEMO_001', '物流异常投诉需要主管决策', 'SupervisorAgent', '建议补发并同步物流 Agent 跟进异常件', '处理中');

INSERT INTO human_agent_status (
  status_id, team_name, online_agents, queue_count,
  estimated_wait_minutes, working_hours, status
) VALUES
('HAS_DEMO_001', 'general_service', 5, 3, 4, '09:00-22:00', '正常'),
('HAS_DEMO_002', 'refund_specialist', 2, 1, 6, '09:00-22:00', '正常'),
('HAS_DEMO_003', 'complaint_specialist', 1, 4, 12, '09:00-21:00', '正常');

INSERT INTO agent_audit_logs (
  audit_id, agent_name, tool_name, user_request, execution_result,
  success, workflow_id, session_id, executed_at
) VALUES
('AUD_DEMO_001', 'ProductAgent', 'product_query', '帮我推荐一款适合直播间购买的手机', JSON_OBJECT('命中商品','星耀 X1 Pro 5G 手机','库存','有货','推荐理由','影像和续航适合高频使用'), 1, 'WF_DEMO_PRODUCT_001', 'demo-minimal-session', DATE_SUB(NOW(), INTERVAL 3 HOUR)),
('AUD_DEMO_002', 'LogisticsAgent', 'logistics_query', '我的扫地机器人物流为什么异常', JSON_OBJECT('订单','ORD_DEMO_003','物流状态','配送异常','处理建议','建议补发或赔付'), 1, 'WF_DEMO_LOGISTICS_001', 'demo-minimal-session', DATE_SUB(NOW(), INTERVAL 2 HOUR)),
('AUD_DEMO_003', 'RefundAgent', 'refund_apply', '查询耳机退款进度', JSON_OBJECT('退款单','REF_DEMO_001','状态','处理中','预计','1-3个工作日完成审核'), 1, 'WF_DEMO_REFUND_001', 'demo-minimal-session', DATE_SUB(NOW(), INTERVAL 1 HOUR));

INSERT INTO workflow_runtime_records (
  workflow_id, current_state, current_agent, fsm_state, slot_state,
  checkpoint_info, resume_info
) VALUES
('WF_DEMO_PRODUCT_001', '已完成', 'ProductAgent', JSON_OBJECT('状态','商品推荐'), JSON_OBJECT('keyword','手机'), JSON_OBJECT('trace','product_query'), JSON_OBJECT()),
('WF_DEMO_REFUND_001', '运行中', 'RefundAgent', JSON_OBJECT('状态','退款进度查询'), JSON_OBJECT('order_id','ORD_DEMO_002','refund_id','REF_DEMO_001'), JSON_OBJECT('checkpoint_id','CHK_REFUND_DEMO'), JSON_OBJECT('resume_supported', true)),
('WF_DEMO_COMPLAINT_001', '主管介入中', 'SupervisorAgent', JSON_OBJECT('状态','投诉升级'), JSON_OBJECT('complaint_id','CMP_DEMO_001','order_id','ORD_DEMO_003'), JSON_OBJECT('checkpoint_id','CHK_COMPLAINT_DEMO'), JSON_OBJECT('resume_node','supervisor_review'));
