import ProductDetailClient from "./product-detail-client";

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ productId: string }>;
}) {
  const { productId } = await params;
  return <ProductDetailClient productId={productId} />;
}
