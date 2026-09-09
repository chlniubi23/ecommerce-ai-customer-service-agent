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
TRUNCATE TABLE user_addresses;
TRUNCATE TABLE users;

SET FOREIGN_KEY_CHECKS = 1;
