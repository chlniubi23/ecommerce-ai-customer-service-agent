"""Business repositories used by Agent tools and workflow persistence."""

from __future__ import annotations

import uuid
from typing import Any

from app.database.connection import MySQLRepository, json_dumps, json_loads


def _like(value: str) -> str:
    return f"%{value.strip()}%"


def _numeric_id(prefix: str, digits: int = 12) -> str:
    value = str(uuid.uuid4().int % (10**digits)).zfill(digits)
    return f"{prefix}{value}"


class UserRepository(MySQLRepository):
    def find_by_login(self, login: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT user_id, username, email, phone, password_hash, full_name,
                   status, created_at, last_login_at
            FROM users
            WHERE username = %s OR email = %s OR phone = %s
            LIMIT 1
            """,
            (login, login, login),
        )

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        user = self.fetch_one(
            """
            SELECT user_id, username, email, phone, full_name, status, created_at, last_login_at
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        if not user:
            return None
        user["addresses"] = self.fetch_all(
            """
            SELECT address_id, receiver_name, phone, province, city, district,
                   address_line, postal_code, is_default
            FROM user_addresses
            WHERE user_id = %s AND status IN ('active', '正常')
            ORDER BY is_default DESC, created_at DESC
            """,
            (user_id,),
        )
        return user

    def create_user(
        self,
        username: str,
        email: str,
        phone: str,
        password_hash: str,
        full_name: str,
    ) -> dict[str, Any]:
        user_id = f"USR{uuid.uuid4().hex[:12].upper()}"
        self.execute(
            """
            INSERT INTO users (
                user_id, username, email, phone, password_hash, full_name,
                status, created_at, updated_at, last_login_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, '正常', NOW(), NOW(), NOW())
            """,
            (user_id, username, email, phone, password_hash, full_name),
        )
        self.execute(
            """
            INSERT INTO user_addresses (
                address_id, user_id, receiver_name, phone, province, city,
                district, address_line, postal_code, is_default, status,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, '上海市', '上海市', '浦东新区',
                    '演示平台默认收货地址', '200000', 1, '正常', NOW(), NOW())
            """,
            (f"ADDR{uuid.uuid4().hex[:12].upper()}", user_id, full_name, phone),
        )
        created = self.get_by_id(user_id)
        if not created:
            raise RuntimeError("User was inserted but could not be loaded")
        return created

    def add_address(
        self,
        user_id: str,
        receiver_name: str,
        phone: str,
        province: str,
        city: str,
        district: str,
        address_line: str,
        postal_code: str = "",
        is_default: bool = False,
    ) -> dict[str, Any]:
        address_id = f"ADDR{uuid.uuid4().hex[:12].upper()}"
        if is_default:
            self.execute("UPDATE user_addresses SET is_default = 0 WHERE user_id = %s", (user_id,))
        self.execute(
            """
            INSERT INTO user_addresses (
                address_id, user_id, receiver_name, phone, province, city,
                district, address_line, postal_code, is_default, status,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '正常', NOW(), NOW())
            """,
            (
                address_id,
                user_id,
                receiver_name,
                phone,
                province,
                city,
                district,
                address_line,
                postal_code,
                1 if is_default else 0,
            ),
        )
        row = self.fetch_one(
            """
            SELECT address_id, receiver_name, phone, province, city, district,
                   address_line, postal_code, is_default
            FROM user_addresses
            WHERE address_id = %s
            """,
            (address_id,),
        )
        if not row:
            raise RuntimeError("Address was inserted but could not be loaded")
        return row


class ProductRepository(MySQLRepository):
    ACTIVE_STATUSES = ("active", "draft", "archived", "上架", "预售", "售罄", "下架")

    def list_products(
        self,
        keyword: str = "",
        category_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        conditions = ["p.product_status IN ('active', 'draft', 'archived', '上架', '预售', '售罄', '下架')"]
        params: list[Any] = []
        if keyword:
            conditions.append(
                """
                (
                  p.product_name LIKE %s OR p.description LIKE %s OR p.tags LIKE %s
                  OR b.brand_name LIKE %s OR c.category_name LIKE %s OR p.sku_id LIKE %s
                )
                """
            )
            params.extend([_like(keyword)] * 6)
        if category_id:
            conditions.append("(p.category_id = %s OR c.parent_id = %s)")
            params.extend([category_id, category_id])

        rows = self.fetch_all(
            f"""
            SELECT p.product_id, p.sku_id, p.product_name, p.description,
                   p.brand_id, b.brand_name, p.category_id, c.category_name,
                   c.category_path, p.price, p.currency, p.product_status,
                   p.tags, p.attributes, i.quantity, i.available_quantity,
                   i.reserved_quantity, i.safety_stock, i.inventory_status,
                   p.updated_at
            FROM products p
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN inventory i ON i.sku_id = p.sku_id
            WHERE {' AND '.join(conditions)}
            ORDER BY p.product_status IN ('active', '上架') DESC, i.available_quantity DESC, p.updated_at DESC
            LIMIT %s
            """,
            tuple(params + [limit]),
        )
        for row in rows:
            row["tags"] = json_loads(row.get("tags"), [])
            row["attributes"] = json_loads(row.get("attributes"), {})
            row["images"] = self.get_product_images(row["product_id"])
        return rows

    def get_product(self, product_id: str) -> dict[str, Any] | None:
        rows = self.fetch_all(
            """
            SELECT p.product_id, p.sku_id, p.product_name, p.description,
                   p.brand_id, b.brand_name, p.category_id, c.category_name,
                   c.category_path, p.price, p.currency, p.product_status,
                   p.version, p.tags, p.attributes, i.quantity,
                   i.available_quantity, i.reserved_quantity, i.safety_stock,
                   i.inventory_status, p.published_at, p.created_at, p.updated_at
            FROM products p
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN inventory i ON i.sku_id = p.sku_id
            WHERE p.product_id = %s
            LIMIT 1
            """,
            (product_id,),
        )
        if not rows:
            return None
        product = rows[0]
        product["tags"] = json_loads(product.get("tags"), [])
        product["attributes"] = json_loads(product.get("attributes"), {})
        product["images"] = self.get_product_images(product_id)
        return product

    def list_categories(self) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT category_id, parent_id, category_name, category_level,
                   category_path, category_status, sort_order
            FROM categories
            WHERE category_status IN ('active', '正常')
            ORDER BY category_level ASC, sort_order ASC, category_name ASC
            """
        )

    def search_products(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT p.product_id, p.sku_id, p.product_name, p.description, p.brand_id,
                   b.brand_name, p.category_id, c.category_name, c.category_path,
                   p.price, p.currency, p.product_status, p.tags, p.attributes,
                   i.quantity, i.available_quantity, i.reserved_quantity,
                   i.safety_stock, i.inventory_status, p.updated_at
            FROM products p
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN inventory i ON i.sku_id = p.sku_id
            WHERE p.product_status IN ('active', 'draft', 'archived', '上架', '预售', '售罄', '下架')
              AND (
                p.product_name LIKE %s OR p.description LIKE %s OR p.tags LIKE %s
                OR b.brand_name LIKE %s OR c.category_name LIKE %s OR p.sku_id LIKE %s
              )
            ORDER BY
              CASE WHEN p.product_name LIKE %s THEN 0 ELSE 1 END,
              p.product_status IN ('active', '上架') DESC,
              i.available_quantity DESC,
              p.updated_at DESC
            LIMIT %s
            """,
            (
                _like(keyword),
                _like(keyword),
                _like(keyword),
                _like(keyword),
                _like(keyword),
                _like(keyword),
                _like(keyword),
                limit,
            ),
        )
        for row in rows:
            row["tags"] = json_loads(row.get("tags"), [])
            row["attributes"] = json_loads(row.get("attributes"), {})
            row["images"] = self.get_product_images(row["product_id"])
        return rows

    def get_by_sku_or_name(self, product_name: str) -> dict[str, Any] | None:
        rows = self.search_products(product_name, limit=1)
        return rows[0] if rows else None

    def get_product_images(self, product_id: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT image_id, image_url, alt_text, is_primary, sort_order
            FROM product_images
            WHERE product_id = %s
            ORDER BY is_primary DESC, sort_order ASC
            """,
            (product_id,),
        )

    def get_inventory(self, product_name: str) -> dict[str, Any] | None:
        return self.get_by_sku_or_name(product_name)


class ProductRecommendationRepository(MySQLRepository):
    """基于用户真实购买历史的个性化推荐。

    区别于框架空转：这里从用户已下单的 order_items 反推偏好品类/品牌，
    再在同品类里找"有货、未买过"的商品推荐，并给出可解释的推荐理由。
    没有历史时兜底为热门有货商品，保证任何用户都有推荐可给。
    """

    def _purchased_products(self, user_id: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT oi.product_id, oi.product_name, p.category_id, c.category_name,
                   p.brand_id, b.brand_name, COUNT(*) AS buy_count
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.order_id
            LEFT JOIN products p ON p.product_id = oi.product_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            WHERE o.user_id = %s
            GROUP BY oi.product_id, oi.product_name, p.category_id, c.category_name,
                     p.brand_id, b.brand_name
            """,
            (user_id,),
        )

    def recommend_for_user(self, user_id: str, limit: int = 5) -> dict[str, Any]:
        purchased = self._purchased_products(user_id)
        purchased_ids = [row["product_id"] for row in purchased if row.get("product_id")]
        preferred_categories = sorted(
            {(row["category_id"], row.get("category_name")) for row in purchased if row.get("category_id")},
            key=lambda item: str(item[1] or ""),
        )
        preferred_brands = sorted(
            {(row["brand_id"], row.get("brand_name")) for row in purchased if row.get("brand_id")},
            key=lambda item: str(item[1] or ""),
        )
        category_ids = [cid for cid, _ in preferred_categories]

        recommendations: list[dict[str, Any]] = []
        if category_ids:
            recommendations = self._candidates_in_categories(category_ids, purchased_ids, limit)

        # 兜底：无历史 / 同品类没货时，用热门有货商品补齐，保证不空转。
        if len(recommendations) < limit:
            fallback = self._popular_in_stock(
                exclude_ids=purchased_ids + [r["product_id"] for r in recommendations],
                limit=limit - len(recommendations),
            )
            for row in fallback:
                row.setdefault("reason", "近期热门且有货，值得看看")
            recommendations.extend(fallback)

        return {
            "user_id": user_id,
            "has_history": bool(purchased_ids),
            "preferred_categories": [name for _, name in preferred_categories if name],
            "preferred_brands": [name for _, name in preferred_brands if name],
            "recommendations": recommendations[:limit],
        }

    def _candidates_in_categories(
        self, category_ids: list[str], exclude_ids: list[str], limit: int
    ) -> list[dict[str, Any]]:
        cat_placeholders = ", ".join(["%s"] * len(category_ids))
        exclude_clause = ""
        params: list[Any] = list(category_ids)
        if exclude_ids:
            exclude_clause = f"AND p.product_id NOT IN ({', '.join(['%s'] * len(exclude_ids))})"
            params.extend(exclude_ids)
        params.append(limit)
        rows = self.fetch_all(
            f"""
            SELECT p.product_id, p.product_name, p.price, p.currency,
                   b.brand_name, c.category_name,
                   i.available_quantity, i.inventory_status
            FROM products p
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN inventory i ON i.sku_id = p.sku_id
            WHERE p.category_id IN ({cat_placeholders})
              {exclude_clause}
              AND COALESCE(i.available_quantity, 0) > 0
            ORDER BY i.available_quantity DESC, p.updated_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        for row in rows:
            row["in_stock"] = True
            row["reason"] = f"和你买过的「{row.get('category_name') or '同类'}」商品同品类，当前有货"
        return rows

    def _popular_in_stock(self, exclude_ids: list[str], limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        exclude_clause = ""
        params: list[Any] = []
        if exclude_ids:
            exclude_clause = f"WHERE p.product_id NOT IN ({', '.join(['%s'] * len(exclude_ids))}) AND COALESCE(i.available_quantity, 0) > 0"
            params.extend(exclude_ids)
        else:
            exclude_clause = "WHERE COALESCE(i.available_quantity, 0) > 0"
        params.append(limit)
        rows = self.fetch_all(
            f"""
            SELECT p.product_id, p.product_name, p.price, p.currency,
                   b.brand_name, c.category_name,
                   i.available_quantity, i.inventory_status
            FROM products p
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            LEFT JOIN inventory i ON i.sku_id = p.sku_id
            {exclude_clause}
            ORDER BY i.available_quantity DESC, p.updated_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        for row in rows:
            row["in_stock"] = True
        return rows


class OrderRepository(MySQLRepository):
    def list_user_orders(self, user_id: str) -> list[dict[str, Any]]:
        orders = self.fetch_all(
            """
            SELECT o.order_id, o.user_id, o.order_status, o.payment_status,
                   o.shipping_status, o.receipt_status, o.total_amount,
                   o.currency, o.created_at, o.paid_at, o.completed_at,
                   s.current_status AS logistics_status, s.estimated_delivery_at
            FROM orders o
            LEFT JOIN logistics_shipments s ON s.order_id = o.order_id
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC
            """,
            (user_id,),
        )
        for order in orders:
            order["items"] = self.fetch_all(
                """
                SELECT order_item_id, product_id, sku_id, product_name,
                       quantity, unit_price, line_amount
                FROM order_items
                WHERE order_id = %s
                ORDER BY order_item_id
                """,
                (order["order_id"],),
            )
        return orders

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        order = self.fetch_one(
            """
            SELECT o.order_id, o.user_id, u.username, u.full_name, o.order_status,
                   o.payment_status, o.shipping_status, o.receipt_status,
                   o.total_amount, o.currency, o.created_at, o.paid_at, o.completed_at,
                   a.receiver_name, a.phone AS receiver_phone, a.province, a.city,
                   a.district, a.address_line
            FROM orders o
            JOIN users u ON u.user_id = o.user_id
            LEFT JOIN user_addresses a ON a.address_id = o.shipping_address_id
            WHERE o.order_id = %s
            """,
            (order_id,),
        )
        if not order:
            return None
        order["items"] = self.fetch_all(
            """
            SELECT oi.order_item_id, oi.product_id, oi.sku_id, oi.product_name,
                   oi.quantity, oi.unit_price, oi.line_amount, p.product_status,
                   b.brand_name, c.category_name
            FROM order_items oi
            LEFT JOIN products p ON p.product_id = oi.product_id
            LEFT JOIN brands b ON b.brand_id = p.brand_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            WHERE oi.order_id = %s
            ORDER BY oi.order_item_id
            """,
            (order_id,),
        )
        return order

    def create_order(self, user_id: str, product_id: str, quantity: int = 1) -> dict[str, Any]:
        product = ProductRepository().get_product(product_id)
        if not product:
            raise ValueError(f"Product {product_id} does not exist")
        user = UserRepository().get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} does not exist")

        default_address = self.fetch_one(
            """
            SELECT address_id
            FROM user_addresses
            WHERE user_id = %s AND status IN ('active', '正常')
            ORDER BY is_default DESC, created_at DESC
            LIMIT 1
            """,
            (user_id,),
        )
        order_id = _numeric_id("ORD")
        item_id = f"OI{uuid.uuid4().hex[:12].upper()}"
        line_amount = float(product["price"]) * quantity
        self.execute(
            """
            INSERT INTO orders (
                order_id, user_id, shipping_address_id, order_status,
                payment_status, shipping_status, receipt_status, total_amount,
                currency, created_at, paid_at, completed_at, updated_at
            )
            VALUES (%s, %s, %s, '已支付', '已支付', '待发货', '未收货',
                    %s, %s, NOW(), NOW(), NULL, NOW())
            """,
            (
                order_id,
                user_id,
                default_address["address_id"] if default_address else None,
                line_amount,
                product["currency"],
            ),
        )
        self.execute(
            """
            INSERT INTO order_items (
                order_item_id, order_id, product_id, sku_id, product_name,
                quantity, unit_price, line_amount, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                item_id,
                order_id,
                product_id,
                product["sku_id"],
                product["product_name"],
                quantity,
                product["price"],
                line_amount,
            ),
        )
        shipment_id = f"SHP{uuid.uuid4().hex[:12].upper()}"
        tracking_no = f"TRK{uuid.uuid4().hex[:12].upper()}"
        self.execute(
            """
            INSERT INTO logistics_shipments (
                shipment_id, order_id, carrier_id, tracking_no,
                current_status, current_location, estimated_delivery_at,
                shipped_at, delivered_at, created_at, updated_at
            )
            VALUES (%s, %s, 'CAR001', %s, '待发货', '商家仓库',
                    DATE_ADD(NOW(), INTERVAL 3 DAY), NULL, NULL, NOW(), NOW())
            """,
            (shipment_id, order_id, tracking_no),
        )
        self.execute(
            """
            INSERT INTO logistics_tracking_events (
                event_id, shipment_id, event_time, location, status, description
            )
            VALUES (%s, %s, NOW(), '商家仓库', '待发货',
                    '订单已创建，等待仓库发货')
            """,
            (f"LTE{uuid.uuid4().hex[:12].upper()}", shipment_id),
        )
        created = self.get_order(order_id)
        if not created:
            raise RuntimeError("Order was inserted but could not be loaded")
        return created


class LogisticsRepository(MySQLRepository):
    def get_by_order_id(self, order_id: str) -> dict[str, Any] | None:
        shipment = self.fetch_one(
            """
            SELECT s.shipment_id, s.order_id, s.carrier_id, c.carrier_name,
                   s.tracking_no, s.current_status, s.current_location,
                   s.estimated_delivery_at, s.shipped_at, s.delivered_at, s.updated_at
            FROM logistics_shipments s
            JOIN carriers c ON c.carrier_id = s.carrier_id
            WHERE s.order_id = %s
            """,
            (order_id,),
        )
        if not shipment:
            return None
        shipment["timeline"] = self.fetch_all(
            """
            SELECT event_id, event_time, location, status, description
            FROM logistics_tracking_events
            WHERE shipment_id = %s
            ORDER BY event_time ASC, event_id ASC
            """,
            (shipment["shipment_id"],),
        )
        return shipment


class RefundRepository(MySQLRepository):
    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        return self.fetch_all(
            """
            SELECT r.refund_id, r.order_id, r.user_id, r.refund_reason,
                   r.refund_amount, r.audit_status, r.refund_status,
                   r.created_at, r.updated_at, o.order_status
            FROM refunds r
            JOIN orders o ON o.order_id = r.order_id
            WHERE r.user_id = %s
            ORDER BY r.created_at DESC
            """,
            (user_id,),
        )

    def get_by_order_id(self, order_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT refund_id, order_id, user_id, refund_reason, refund_amount,
                   audit_status, refund_status, created_at, updated_at
            FROM refunds
            WHERE order_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (order_id,),
        )

    def create_refund(self, order_id: str, reason: str) -> dict[str, Any]:
        order = OrderRepository().get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} does not exist")

        refund_id = f"REF{uuid.uuid4().hex[:12].upper()}"
        self.execute(
            """
            INSERT INTO refunds (
                refund_id, order_id, user_id, refund_reason, refund_amount,
                audit_status, refund_status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, '待审核', '待处理', NOW(), NOW())
            """,
            (refund_id, order_id, order["user_id"], reason, order["total_amount"]),
        )
        created = self.get_by_order_id(order_id)
        if not created:
            raise RuntimeError("Refund was inserted but could not be loaded")
        return created


class ComplaintRepository(MySQLRepository):
    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        complaints = self.fetch_all(
            """
            SELECT complaint_id, ticket_id, user_id, order_id, complaint_type,
                   content, complaint_status, priority, created_at, updated_at, closed_at
            FROM complaints
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        for complaint in complaints:
            complaint["escalations"] = self.fetch_all(
                """
                SELECT escalation_id, escalation_reason, escalated_to,
                       supervisor_result, escalation_status, created_at, resolved_at
                FROM complaint_escalations
                WHERE complaint_id = %s
                ORDER BY created_at DESC
                """,
                (complaint["complaint_id"],),
            )
        return complaints

    def create_complaint(
        self,
        content: str,
        complaint_type: str = "general",
        order_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if order_id and not user_id:
            order = OrderRepository().get_order(order_id)
            if order:
                user_id = order["user_id"]
        if not user_id:
            user_id = self._default_user_id()

        complaint_id = f"CMP{uuid.uuid4().hex[:12].upper()}"
        ticket_id = f"TKT{uuid.uuid4().hex[:12].upper()}"
        self.execute(
            """
            INSERT INTO complaints (
                complaint_id, ticket_id, user_id, order_id, complaint_type,
                content, complaint_status, priority, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, '已提交', '普通', NOW(), NOW())
            """,
            (complaint_id, ticket_id, user_id, order_id, complaint_type, content),
        )
        self.execute(
            """
            INSERT INTO complaint_process_records (
                record_id, complaint_id, handler, action, note, created_at
            )
            VALUES (%s, %s, '投诉 Agent', '已创建', %s, NOW())
            """,
            (f"CPR{uuid.uuid4().hex[:12].upper()}", complaint_id, "投诉已由 Agent 工具创建"),
        )
        created = self.get_by_id(complaint_id)
        if not created:
            raise RuntimeError("Complaint was inserted but could not be loaded")
        return created

    def get_by_id(self, complaint_id: str) -> dict[str, Any] | None:
        complaint = self.fetch_one(
            """
            SELECT complaint_id, ticket_id, user_id, order_id, complaint_type,
                   content, complaint_status, priority, created_at, updated_at, closed_at
            FROM complaints
            WHERE complaint_id = %s
            """,
            (complaint_id,),
        )
        if not complaint:
            return None
        complaint["process_records"] = self.fetch_all(
            """
            SELECT record_id, handler, action, note, created_at
            FROM complaint_process_records
            WHERE complaint_id = %s
            ORDER BY created_at ASC
            """,
            (complaint_id,),
        )
        complaint["escalations"] = self.fetch_all(
            """
            SELECT escalation_id, escalation_reason, escalated_to, supervisor_result,
                   escalation_status, created_at, resolved_at
            FROM complaint_escalations
            WHERE complaint_id = %s
            ORDER BY created_at ASC
            """,
            (complaint_id,),
        )
        return complaint

    def get_by_any_id(self, ref_id: str) -> dict[str, Any] | None:
        """按投诉号或工单号查询投诉（跟进场景用户可能给任一编号）。"""
        complaint = self.get_by_id(ref_id)
        if complaint:
            return complaint
        row = self.fetch_one(
            "SELECT complaint_id FROM complaints WHERE ticket_id = %s",
            (ref_id,),
        )
        if row:
            return self.get_by_id(row["complaint_id"])
        return None

    def get_latest_by_order_id(self, order_id: str) -> dict[str, Any] | None:
        """按订单号查询最近一条投诉（用户说"这个订单我投诉过了"但不记得编号时用）。"""
        if not order_id:
            return None
        row = self.fetch_one(
            """
            SELECT complaint_id FROM complaints
            WHERE order_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (order_id,),
        )
        if row:
            return self.get_by_id(row["complaint_id"])
        return None

    def _default_user_id(self) -> str:
        row = self.fetch_one("SELECT user_id FROM users ORDER BY created_at ASC LIMIT 1")
        if not row:
            raise ValueError("No default user exists for complaint creation")
        return row["user_id"]


class AgentAuditRepository(MySQLRepository):
    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT audit_id, agent_name, tool_name, user_request,
                   execution_result, success, workflow_id, session_id, executed_at
            FROM agent_audit_logs
            ORDER BY executed_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        for row in rows:
            row["execution_result"] = json_loads(row.get("execution_result"), {})
        return rows

    def record(
        self,
        tool_name: str,
        user_request: str,
        execution_result: dict[str, Any],
        agent_name: str = "ToolRuntime",
        workflow_id: str | None = None,
        session_id: str | None = None,
        success: bool = True,
    ) -> None:
        self.execute(
            """
            INSERT INTO agent_audit_logs (
                audit_id, agent_name, tool_name, user_request, execution_result,
                success, workflow_id, session_id, executed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                f"AUD{uuid.uuid4().hex[:12].upper()}",
                agent_name,
                tool_name,
                user_request,
                json_dumps(execution_result),
                1 if success else 0,
                workflow_id,
                session_id,
            ),
        )


class HumanAgentStatusRepository(MySQLRepository):
    def get_status(self, team_name: str = "general_service") -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT status_id, team_name, online_agents, queue_count,
                   estimated_wait_minutes, working_hours, status, updated_at
            FROM human_agent_status
            WHERE team_name = %s AND status IN ('active', '正常')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (team_name,),
        )


class HumanTransferRepository(MySQLRepository):
    """转人工请求仓储：真正把用户加入人工队列（写库 + 队列人数 +1）。

    与只读的 HumanAgentStatusRepository 区分：后者是队列状态快照，
    这里负责"执行转接"这个动作本身——落一条排队记录并把 queue_count 递增，
    使 transfer_human 从"假成功"变为真正达成用户目的。
    """

    def create_transfer_request(
        self,
        team_name: str,
        reason: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        transfer_id = f"HTR{uuid.uuid4().hex[:12].upper()}"
        # 队列人数原子 +1，再读回递增后的真实排队人数作为该用户排队位次。
        # 单条 UPDATE 保证并发下 queue_count 不丢失更新。
        affected = self.execute(
            """
            UPDATE human_agent_status
            SET queue_count = queue_count + 1, updated_at = NOW()
            WHERE team_name = %s AND status IN ('active', '正常')
            """,
            (team_name,),
        )
        if not affected:
            raise ValueError(f"No active human agent queue for team '{team_name}'")

        status = HumanAgentStatusRepository().get_status(team_name)
        if not status:
            raise RuntimeError("Queue was incremented but status could not be reloaded")
        queue_position = status["queue_count"]

        self.execute(
            """
            INSERT INTO human_transfer_requests (
                transfer_id, team_name, user_id, session_id, reason,
                queue_position, transfer_status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'queued', NOW(), NOW())
            """,
            (transfer_id, team_name, user_id, session_id, reason, queue_position),
        )
        created = self.get_by_id(transfer_id)
        if not created:
            raise RuntimeError("Transfer request was inserted but could not be loaded")
        created["estimated_wait_minutes"] = status["estimated_wait_minutes"]
        created["online_agents"] = status["online_agents"]
        created["working_hours"] = status["working_hours"]
        return created

    def get_by_id(self, transfer_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT transfer_id, team_name, user_id, session_id, reason,
                   queue_position, transfer_status, created_at, updated_at
            FROM human_transfer_requests
            WHERE transfer_id = %s
            """,
            (transfer_id,),
        )


class ProactiveEventRepository(MySQLRepository):
    """主动服务事件仓储：业务状态变化时落一条持久化事件。

    与只读的 insight 快照区分：insight 每次都对当前数据重算，无法感知"变化"、
    也分不清新旧；这里以 (user_id, dedup_key) 去重落库，带 unread/read 状态，
    使系统从"进店看板"升级为"事件驱动的主动提醒"。
    """

    def emit(
        self,
        user_id: str,
        event_type: str,
        severity: str,
        title: str,
        description: str,
        action_prompt: str,
        dedup_key: str,
        order_id: str | None = None,
        related_id: str | None = None,
    ) -> dict[str, Any]:
        """落一条主动事件。同一 (user_id, dedup_key) 已存在则不重复插入（去重防刷屏）。"""
        existing = self.fetch_one(
            """
            SELECT event_id FROM proactive_events
            WHERE user_id = %s AND dedup_key = %s
            """,
            (user_id, dedup_key),
        )
        if existing:
            reloaded = self.get_by_id(existing["event_id"])
            if reloaded:
                return reloaded

        event_id = f"PEV{uuid.uuid4().hex[:12].upper()}"
        self.execute(
            """
            INSERT INTO proactive_events (
                event_id, user_id, event_type, severity, title, description,
                action_prompt, order_id, related_id, dedup_key, event_status,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'unread', NOW(), NOW())
            """,
            (
                event_id, user_id, event_type, severity, title, description,
                action_prompt, order_id, related_id, dedup_key,
            ),
        )
        created = self.get_by_id(event_id)
        if not created:
            raise RuntimeError("Proactive event was inserted but could not be loaded")
        return created

    def get_by_id(self, event_id: str) -> dict[str, Any] | None:
        return self.fetch_one(
            """
            SELECT event_id, user_id, event_type, severity, title, description,
                   action_prompt, order_id, related_id, dedup_key, event_status,
                   created_at, updated_at
            FROM proactive_events
            WHERE event_id = %s
            """,
            (event_id,),
        )

    def list_for_user(
        self,
        user_id: str,
        statuses: tuple[str, ...] = ("unread", "read"),
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ", ".join(["%s"] * len(statuses))
        return self.fetch_all(
            f"""
            SELECT event_id, user_id, event_type, severity, title, description,
                   action_prompt, order_id, related_id, dedup_key, event_status,
                   created_at, updated_at
            FROM proactive_events
            WHERE user_id = %s AND event_status IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (user_id, *statuses, limit),
        )

    def mark_read(self, event_id: str) -> None:
        self.execute(
            """
            UPDATE proactive_events
            SET event_status = 'read', updated_at = NOW()
            WHERE event_id = %s
            """,
            (event_id,),
        )


class WorkflowRuntimeRepository(MySQLRepository):
    def list_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.fetch_all(
            """
            SELECT workflow_id, current_state, current_agent, fsm_state,
                   slot_state, checkpoint_info, resume_info, created_at, updated_at
            FROM workflow_runtime_records
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        for row in rows:
            for field in ("fsm_state", "slot_state", "checkpoint_info", "resume_info"):
                row[field] = json_loads(row.get(field), {})
        return rows

    def upsert_runtime_record(
        self,
        workflow_id: str,
        current_state: str,
        current_agent: str,
        fsm_state: dict[str, Any] | None = None,
        slot_state: dict[str, Any] | None = None,
        checkpoint_info: dict[str, Any] | None = None,
        resume_info: dict[str, Any] | None = None,
    ) -> None:
        self.execute(
            """
            INSERT INTO workflow_runtime_records (
                workflow_id, current_state, current_agent, fsm_state, slot_state,
                checkpoint_info, resume_info, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                current_state = VALUES(current_state),
                current_agent = VALUES(current_agent),
                fsm_state = VALUES(fsm_state),
                slot_state = VALUES(slot_state),
                checkpoint_info = VALUES(checkpoint_info),
                resume_info = VALUES(resume_info),
                updated_at = NOW()
            """,
            (
                workflow_id,
                current_state,
                current_agent,
                json_dumps(fsm_state or {}),
                json_dumps(slot_state or {}),
                json_dumps(checkpoint_info or {}),
                json_dumps(resume_info or {}),
            ),
        )

    def get_runtime_record(self, workflow_id: str) -> dict[str, Any] | None:
        record = self.fetch_one(
            """
            SELECT workflow_id, current_state, current_agent, fsm_state, slot_state,
                   checkpoint_info, resume_info, created_at, updated_at
            FROM workflow_runtime_records
            WHERE workflow_id = %s
            """,
            (workflow_id,),
        )
        if not record:
            return None
        for field in ("fsm_state", "slot_state", "checkpoint_info", "resume_info"):
            record[field] = json_loads(record.get(field), {})
        return record


class CouponRepository(MySQLRepository):
    """演示优惠券数据源。

    当前业务库没有优惠券表，这里返回确定性演示数据，让 AI 能真实回答
    "我当前有哪些可用优惠券"。有真实 user_coupons 表后可替换为 SQL 查询。
    """

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        if not user_id:
            return []
        return [
            {
                "coupon_id": "CPN_DEMO_001",
                "coupon_name": "满200减30",
                "coupon_type": "满减券",
                "threshold_amount": 200,
                "discount_amount": 30,
                "coupon_status": "可用",
                "valid_until": "2026-12-31",
                "applicable_scope": "全场通用",
            },
            {
                "coupon_id": "CPN_DEMO_002",
                "coupon_name": "数码专区95折",
                "coupon_type": "折扣券",
                "discount_rate": 0.95,
                "coupon_status": "可用",
                "valid_until": "2026-09-30",
                "applicable_scope": "数码家电",
            },
            {
                "coupon_id": "CPN_DEMO_003",
                "coupon_name": "新人首单立减15",
                "coupon_type": "立减券",
                "discount_amount": 15,
                "coupon_status": "已使用",
                "valid_until": "2026-06-30",
                "applicable_scope": "全场通用",
            },
        ]
