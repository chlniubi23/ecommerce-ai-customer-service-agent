-- Docker 首启种子用户（作为 mysql 镜像 /docker-entrypoint-initdb.d/ 的 02 号脚本）
-- 背景：demo_minimal_cn.sql 只 TRUNCATE 业务表并引用"最新已存在用户"（@demo_user_id），
-- 不创建用户；容器首启时 users 表为空会导致 orders 演示数据导入失败。
-- 本脚本在 demo 之前插入一个演示用户与默认地址，幂等（INSERT IGNORE，重复执行跳过）。
-- 演示账号：demo_user / demo123456（密码 SHA-256 无盐，演示级，与项目鉴权现状一致）。

USE ai_agent_commerce_demo;

SET NAMES utf8mb4;

INSERT IGNORE INTO users (user_id, username, email, phone, password_hash, full_name, status)
VALUES (
  'USR_DEMO_001',
  'demo_user',
  'demo@example.com',
  '13800000001',
  'd2b000ce0875cad8615dd8cf34f788635c959a0ce2b8a977e22caab745380b06',
  '演示用户',
  '正常'
);

INSERT IGNORE INTO user_addresses (
  address_id, user_id, receiver_name, phone,
  province, city, district, address_line, postal_code, is_default, status
) VALUES (
  'ADDR_DEMO_001',
  'USR_DEMO_001',
  '演示用户',
  '13800000001',
  '浙江省',
  '杭州市',
  '西湖区',
  '文三路 100 号演示小区 1 幢 101 室',
  '310012',
  1,
  '正常'
);
