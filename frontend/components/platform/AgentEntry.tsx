"use client";

const OPEN_EVENT = "commerce:open-agent";

export default function AgentEntry({
  userId,
  productId,
  orderId,
  label = "问AI助手",
}: {
  userId?: string;
  productId?: string;
  orderId?: string;
  label?: string;
}) {
  const openAssistant = () => {
    window.dispatchEvent(
      new CustomEvent(OPEN_EVENT, {
        detail: {
          user_id: userId,
          product_id: productId,
          order_id: orderId,
        },
      }),
    );
  };

  return (
    <button type="button" onClick={openAssistant} className="app-button">
      <span className="mr-1.5">✦</span>
      {label}
    </button>
  );
}
