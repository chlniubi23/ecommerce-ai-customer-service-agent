CREATE DATABASE IF NOT EXISTS ai_agent_commerce_demo
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE ai_agent_commerce_demo;

CREATE TABLE IF NOT EXISTS users (
  user_id VARCHAR(32) PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(128) NOT NULL UNIQUE,
  phone VARCHAR(32) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  last_login_at DATETIME NULL,
  INDEX idx_users_status (status),
  INDEX idx_users_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_addresses (
  address_id VARCHAR(32) PRIMARY KEY,
  user_id VARCHAR(32) NOT NULL,
  receiver_name VARCHAR(64) NOT NULL,
  phone VARCHAR(32) NOT NULL,
  province VARCHAR(64) NOT NULL,
  city VARCHAR(64) NOT NULL,
  district VARCHAR(64) NOT NULL,
  address_line VARCHAR(255) NOT NULL,
  postal_code VARCHAR(16) NULL,
  is_default TINYINT(1) NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_addresses_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  INDEX idx_addresses_user (user_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS brands (
  brand_id VARCHAR(32) PRIMARY KEY,
  brand_name VARCHAR(128) NOT NULL UNIQUE,
  description TEXT NULL,
  brand_status VARCHAR(32) NOT NULL DEFAULT 'active',
  tags JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_brands_status (brand_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS categories (
  category_id VARCHAR(32) PRIMARY KEY,
  parent_id VARCHAR(32) NULL,
  category_name VARCHAR(128) NOT NULL,
  category_level INT NOT NULL,
  category_path VARCHAR(512) NOT NULL,
  category_status VARCHAR(32) NOT NULL DEFAULT 'active',
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_categories_parent FOREIGN KEY (parent_id) REFERENCES categories(category_id),
  INDEX idx_categories_parent (parent_id),
  INDEX idx_categories_path (category_path),
  INDEX idx_categories_status (category_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS product_collections (
  collection_id VARCHAR(32) PRIMARY KEY,
  collection_name VARCHAR(128) NOT NULL,
  description TEXT NULL,
  collection_status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS products (
  product_id VARCHAR(32) PRIMARY KEY,
  sku_id VARCHAR(32) NOT NULL UNIQUE,
  brand_id VARCHAR(32) NOT NULL,
  category_id VARCHAR(32) NOT NULL,
  product_name VARCHAR(255) NOT NULL,
  description TEXT NULL,
  price DECIMAL(12,2) NOT NULL,
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  product_status VARCHAR(32) NOT NULL DEFAULT 'active',
  version INT NOT NULL DEFAULT 1,
  tags JSON NULL,
  attributes JSON NULL,
  published_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_products_brand FOREIGN KEY (brand_id) REFERENCES brands(brand_id),
  CONSTRAINT fk_products_category FOREIGN KEY (category_id) REFERENCES categories(category_id),
  INDEX idx_products_name (product_name),
  INDEX idx_products_status (product_status),
  INDEX idx_products_brand_category (brand_id, category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS product_images (
  image_id VARCHAR(32) PRIMARY KEY,
  product_id VARCHAR(32) NOT NULL,
  image_url VARCHAR(512) NOT NULL,
  alt_text VARCHAR(255) NULL,
  is_primary TINYINT(1) NOT NULL DEFAULT 0,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_product_images_product FOREIGN KEY (product_id) REFERENCES products(product_id),
  INDEX idx_images_product (product_id, is_primary)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS product_collection_items (
  collection_id VARCHAR(32) NOT NULL,
  product_id VARCHAR(32) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  PRIMARY KEY (collection_id, product_id),
  CONSTRAINT fk_collection_items_collection FOREIGN KEY (collection_id) REFERENCES product_collections(collection_id),
  CONSTRAINT fk_collection_items_product FOREIGN KEY (product_id) REFERENCES products(product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inventory (
  inventory_id VARCHAR(32) PRIMARY KEY,
  product_id VARCHAR(32) NOT NULL,
  sku_id VARCHAR(32) NOT NULL,
  quantity INT NOT NULL DEFAULT 0,
  available_quantity INT NOT NULL DEFAULT 0,
  reserved_quantity INT NOT NULL DEFAULT 0,
  safety_stock INT NOT NULL DEFAULT 0,
  inventory_status VARCHAR(32) NOT NULL DEFAULT 'in_stock',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES products(product_id),
  UNIQUE KEY uk_inventory_sku (sku_id),
  INDEX idx_inventory_status (inventory_status),
  INDEX idx_inventory_available (available_quantity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inventory_history (
  history_id VARCHAR(32) PRIMARY KEY,
  sku_id VARCHAR(32) NOT NULL,
  change_type VARCHAR(32) NOT NULL,
  quantity_delta INT NOT NULL,
  quantity_after INT NOT NULL,
  reason VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_inventory_history_sku (sku_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS orders (
  order_id VARCHAR(32) PRIMARY KEY,
  user_id VARCHAR(32) NOT NULL,
  shipping_address_id VARCHAR(32) NULL,
  order_status VARCHAR(32) NOT NULL,
  payment_status VARCHAR(32) NOT NULL,
  shipping_status VARCHAR(32) NOT NULL,
  receipt_status VARCHAR(32) NOT NULL,
  total_amount DECIMAL(12,2) NOT NULL,
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paid_at DATETIME NULL,
  completed_at DATETIME NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_orders_address FOREIGN KEY (shipping_address_id) REFERENCES user_addresses(address_id),
  INDEX idx_orders_user (user_id, created_at),
  INDEX idx_orders_status (order_status, payment_status, shipping_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS order_items (
  order_item_id VARCHAR(32) PRIMARY KEY,
  order_id VARCHAR(32) NOT NULL,
  product_id VARCHAR(32) NOT NULL,
  sku_id VARCHAR(32) NOT NULL,
  product_name VARCHAR(255) NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL,
  line_amount DECIMAL(12,2) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) REFERENCES products(product_id),
  INDEX idx_order_items_order (order_id),
  INDEX idx_order_items_product (product_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS carriers (
  carrier_id VARCHAR(32) PRIMARY KEY,
  carrier_name VARCHAR(128) NOT NULL,
  service_phone VARCHAR(32) NULL,
  carrier_status VARCHAR(32) NOT NULL DEFAULT 'active'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS logistics_shipments (
  shipment_id VARCHAR(32) PRIMARY KEY,
  order_id VARCHAR(32) NOT NULL UNIQUE,
  carrier_id VARCHAR(32) NOT NULL,
  tracking_no VARCHAR(64) NOT NULL UNIQUE,
  current_status VARCHAR(32) NOT NULL,
  current_location VARCHAR(128) NULL,
  estimated_delivery_at DATETIME NULL,
  shipped_at DATETIME NULL,
  delivered_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_shipments_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_shipments_carrier FOREIGN KEY (carrier_id) REFERENCES carriers(carrier_id),
  INDEX idx_shipments_status (current_status),
  INDEX idx_shipments_tracking (tracking_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS logistics_tracking_events (
  event_id VARCHAR(32) PRIMARY KEY,
  shipment_id VARCHAR(32) NOT NULL,
  event_time DATETIME NOT NULL,
  location VARCHAR(128) NULL,
  status VARCHAR(32) NOT NULL,
  description VARCHAR(255) NOT NULL,
  CONSTRAINT fk_tracking_shipment FOREIGN KEY (shipment_id) REFERENCES logistics_shipments(shipment_id),
  INDEX idx_tracking_shipment_time (shipment_id, event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS refunds (
  refund_id VARCHAR(32) PRIMARY KEY,
  order_id VARCHAR(32) NOT NULL,
  user_id VARCHAR(32) NOT NULL,
  refund_reason VARCHAR(255) NOT NULL,
  refund_amount DECIMAL(12,2) NOT NULL,
  audit_status VARCHAR(32) NOT NULL,
  refund_status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_refunds_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  CONSTRAINT fk_refunds_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  INDEX idx_refunds_order (order_id),
  INDEX idx_refunds_user_status (user_id, refund_status),
  INDEX idx_refunds_audit (audit_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS complaints (
  complaint_id VARCHAR(32) PRIMARY KEY,
  ticket_id VARCHAR(32) NOT NULL UNIQUE,
  user_id VARCHAR(32) NOT NULL,
  order_id VARCHAR(32) NULL,
  complaint_type VARCHAR(64) NOT NULL,
  content TEXT NOT NULL,
  complaint_status VARCHAR(32) NOT NULL,
  priority VARCHAR(32) NOT NULL DEFAULT 'normal',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  closed_at DATETIME NULL,
  CONSTRAINT fk_complaints_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_complaints_order FOREIGN KEY (order_id) REFERENCES orders(order_id),
  INDEX idx_complaints_user (user_id, complaint_status),
  INDEX idx_complaints_order (order_id),
  INDEX idx_complaints_status (complaint_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS complaint_process_records (
  record_id VARCHAR(32) PRIMARY KEY,
  complaint_id VARCHAR(32) NOT NULL,
  handler VARCHAR(64) NOT NULL,
  action VARCHAR(64) NOT NULL,
  note TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_complaint_records_complaint FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id),
  INDEX idx_complaint_records_complaint (complaint_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS complaint_escalations (
  escalation_id VARCHAR(32) PRIMARY KEY,
  complaint_id VARCHAR(32) NOT NULL,
  escalation_reason VARCHAR(255) NOT NULL,
  escalated_to VARCHAR(64) NOT NULL,
  current_owner VARCHAR(64) NOT NULL,
  supervisor_result TEXT NULL,
  escalation_status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME NULL,
  CONSTRAINT fk_complaint_escalations_complaint FOREIGN KEY (complaint_id) REFERENCES complaints(complaint_id),
  INDEX idx_complaint_escalations_status (escalation_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS supervisor_escalations (
  supervisor_escalation_id VARCHAR(32) PRIMARY KEY,
  source_agent VARCHAR(64) NOT NULL,
  workflow_id VARCHAR(64) NULL,
  related_complaint_id VARCHAR(32) NULL,
  escalation_reason VARCHAR(255) NOT NULL,
  current_owner VARCHAR(64) NOT NULL,
  supervisor_result TEXT NULL,
  escalation_status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_supervisor_complaint FOREIGN KEY (related_complaint_id) REFERENCES complaints(complaint_id),
  INDEX idx_supervisor_source (source_agent, escalation_status),
  INDEX idx_supervisor_workflow (workflow_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS human_agent_status (
  status_id VARCHAR(32) PRIMARY KEY,
  team_name VARCHAR(64) NOT NULL,
  online_agents INT NOT NULL DEFAULT 0,
  queue_count INT NOT NULL DEFAULT 0,
  estimated_wait_minutes INT NOT NULL DEFAULT 0,
  working_hours VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_human_agent_status (team_name, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 转人工请求：每次"转人工"都在此落一条真实排队记录（write），
-- 而非仅读取 human_agent_status 的排队数。用户由此真正进入人工队列。
CREATE TABLE IF NOT EXISTS human_transfer_requests (
  transfer_id VARCHAR(32) PRIMARY KEY,
  team_name VARCHAR(64) NOT NULL,
  user_id VARCHAR(32) NULL,
  session_id VARCHAR(64) NULL,
  reason VARCHAR(255) NOT NULL,
  queue_position INT NOT NULL DEFAULT 0,
  transfer_status VARCHAR(32) NOT NULL DEFAULT 'queued',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_transfer_team_status (team_name, transfer_status),
  INDEX idx_transfer_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_audit_logs (
  audit_id VARCHAR(32) PRIMARY KEY,
  agent_name VARCHAR(64) NOT NULL,
  tool_name VARCHAR(64) NOT NULL,
  user_request TEXT NULL,
  execution_result JSON NULL,
  success TINYINT(1) NOT NULL DEFAULT 1,
  workflow_id VARCHAR(64) NULL,
  session_id VARCHAR(64) NULL,
  executed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_audit_agent_tool (agent_name, tool_name, executed_at),
  INDEX idx_audit_workflow (workflow_id),
  INDEX idx_audit_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS workflow_runtime_records (
  workflow_id VARCHAR(64) PRIMARY KEY,
  current_state VARCHAR(64) NOT NULL,
  current_agent VARCHAR(64) NOT NULL,
  fsm_state JSON NULL,
  slot_state JSON NULL,
  checkpoint_info JSON NULL,
  resume_info JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_workflow_agent_state (current_agent, current_state),
  INDEX idx_workflow_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
