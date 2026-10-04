-- Docker 首启种子用户（作为 mysql 镜像 /docker-entrypoint-initdb.d/ 的 02 号脚本）
-- 背景：demo_minimal_cn.sql 只 TRUNCATE 业务表并引用"最新已存在用户"（@demo_user_id），
-- 不创建用户；容器首启时 users 表为空会导致 orders 演示数据导入失败。
-- 本脚本在 demo 之前插入一个演示用户与默认地址，幂等（INSERT IGNORE，重复执行跳过）。
-- 演示账号与前端登录页预填提示一致：手机号 13560569291 / 密码 123456
-- （SHA-256 无盐，演示级，与项目鉴权现状一致；demo_minimal_cn.sql 的订单经
--   @demo_user_id 全部挂在该用户名下，登录后即可见全部演示订单）。

USE ai_agent_commerce_demo;

SET NAMES utf8mb4;

INSERT IGNORE INTO users (user_id, username, email, phone, password_hash, full_name, status)
VALUES (
  'USR_DEMO_001',
  'demo_user',
  'demo@example.com',
  '13560569291',
  '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92',
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
  '13560569291',
  '浙江省',
  '杭州市',
  '西湖区',
  '文三路 100 号演示小区 1 幢 101 室',
  '310012',
  1,
  '正常'
);
