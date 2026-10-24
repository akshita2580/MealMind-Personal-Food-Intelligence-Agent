import { useState, useEffect } from 'react'
import { MapPin, Search, ShoppingCart, Package } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getAddresses, searchProducts } from '@/services/api'

interface Address {
  id: string;
  addressLine: string;
  addressCategory?: string;
  addressTag?: string;
  phoneNumber?: string;
}

interface Product {
  // ID fields
  productId?: string;
  id?: string;
  spinId?: string;
  product_id?: string;
  parentProductId?: string;
  
  // Name fields
  displayName?: string;
  name?: string;
  product_name?: string;
  title?: string;
  
  // Brand and metadata
  brand?: string;
  inStock?: boolean;
  isAvail?: boolean;
  isPromoted?: boolean;
  badges?: any[];
  
  // Variations (Swiggy Instamart structure)
  variations?: Array<{
    price?: any; // Can be number or object with mrp/offer_price
    mrp?: number;
    quantity?: string;
    size?: string;
  }>;
  
  // Direct price fields (fallback)
  price?: number;
  product_price?: number;
  mrp?: number;
  
  // Image fields
  image_url?: string;
  imageUrl?: string;
  image?: string;
  
  // Other fields
  category?: string;
  quantity?: string;
  pack_size?: string;
  size?: string;
}

export default function Instamart() {
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Cart state
  const [cart, setCart] = useState<Record<string, { product: Product; quantity: number }>>({})

  const addToCart = (product: Product, productId: string) => {
    setCart(prev => ({
      ...prev,
      [productId]: {
        product,
        quantity: (prev[productId]?.quantity || 0) + 1
      }
    }))
  }

  const cartList = Object.values(cart)
  const cartItemCount = cartList.reduce((sum, ci) => sum + ci.quantity, 0)
  const cartTotalAmount = cartList.reduce((sum, ci) => {
    let price = 0
    if (ci.product.variations && Array.isArray(ci.product.variations) && ci.product.variations.length > 0) {
      const firstVar = ci.product.variations[0]
      price = firstVar.price?.mrp || firstVar.price?.offer_price || firstVar.mrp || firstVar.price || 0
    }
    if (price === 0) {
      price = ci.product.price || ci.product.product_price || ci.product.mrp || 0
    }
    return sum + (price * ci.quantity)
  }, 0)

  useEffect(() => {
    loadAddresses()
  }, [])

  const loadAddresses = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getAddresses()
      console.log('Addresses response:', data)
      
      if (data.addresses && data.addresses.length > 0) {
        console.log('First address:', data.addresses[0])
        setAddresses(data.addresses)
        setSelectedAddress(data.addresses[0])
      } else {
        setError('No addresses found')
      }
    } catch (err) {
      console.error('Load addresses error:', err)
      setError(err instanceof Error ? err.message : 'Failed to load addresses')
    } finally {
      setLoading(false)
    }
  }

  const handleSearch = async () => {
    if (!selectedAddress || !searchQuery.trim()) return

    try {
      setSearching(true)
      setError(null)
      const data = await searchProducts(selectedAddress.id, searchQuery)
      console.log('=== INSTAMART RAW RESPONSE ===')
      console.log('Product search results:', data)
      console.log('Product search results type:', typeof data)
      console.log('Product search results keys:', Object.keys(data || {}))
      
      // Handle different response formats
      let productsList = []
      if (Array.isArray(data)) {
        console.log('Response is array, length:', data.length)
        productsList = data
      } else if (data.products && Array.isArray(data.products)) {
        console.log('Found products array, length:', data.products.length)
        productsList = data.products
      } else if (data.items && Array.isArray(data.items)) {
        console.log('Found items array, length:', data.items.length)
        productsList = data.items
      } else if (data.data && Array.isArray(data.data)) {
        console.log('Found data array, length:', data.data.length)
        productsList = data.data
      } else {
        console.log('Could not find products array in response')
        console.log('Full response:', JSON.stringify(data, null, 2))
      }
      
      console.log('=== EXTRACTED PRODUCTS ===')
      console.log('Extracted products count:', productsList.length)
      if (productsList.length > 0) {
        console.log('First product:', productsList[0])
        console.log('First product keys:', Object.keys(productsList[0] || {}))
      }
      
      setProducts(productsList)
    } catch (err) {
      console.error('Product search error:', err)
      setError(err instanceof Error ? err.message : 'Search failed')
      setProducts([])
    } finally {
      setSearching(false)
    }
  }

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(price)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <ShoppingCart className="h-8 w-8 text-primary" />
          Instamart
        </h1>
        <p className="text-muted-foreground mt-1">
          Shop groceries and essentials
        </p>
      </div>

      {/* Address Selection */}
      {addresses.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <MapPin className="h-5 w-5" />
              Delivery Address
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {addresses.map((addr, idx) => (
                <div
                  key={addr.id || idx}
                  onClick={() => setSelectedAddress(addr)}
                  className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                    selectedAddress?.id === addr.id
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50'
                  }`}
                >
                  <p className="font-medium">{addr.addressLine || 'Address not available'}</p>
                  {addr.addressTag && (
                    <span className="inline-block mt-1 text-xs bg-secondary px-2 py-1 rounded">
                      {addr.addressTag}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search */}
      {selectedAddress && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Search Products</CardTitle>
            <CardDescription>
              Find groceries, vegetables, dairy, and more
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search for milk, eggs, vegetables..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                  className="pl-10"
                />
              </div>
              <Button onClick={handleSearch} disabled={searching || !searchQuery.trim()}>
                {searching ? 'Searching...' : 'Search'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error Message */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="py-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Search Results */}
      {products.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold mb-4">
            Found {products.length} product{products.length > 1 ? 's' : ''}
          </h2>
          <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-4">
            {products.map((product, idx) => {
              // Extract fields based on actual Swiggy Instamart API structure
              const productName = product.displayName || product.name || product.product_name || product.title || 'Product';
              const productBrand = product.brand || '';
              
              // Price is in variations array - get the first variation's price
              let productPrice = 0;
              let productQty = '';
              if (product.variations && Array.isArray(product.variations) && product.variations.length > 0) {
                const firstVariation = product.variations[0];
                productPrice = firstVariation.price?.mrp || firstVariation.price?.offer_price || firstVariation.mrp || firstVariation.price || 0;
                productQty = firstVariation.quantity || firstVariation.size || '';
              }
              
              // Fallback to direct fields if variations not present
              if (productPrice === 0) {
                productPrice = product.price || product.product_price || product.mrp || 0;
              }
              if (!productQty) {
                productQty = product.quantity || product.pack_size || product.size || '';
              }
              
              const productImage = product.image_url || product.imageUrl || product.image;
              const productId = product.productId || product.id || product.spinId || product.product_id || `product-${idx}`;
              
              return (
                <Card key={productId} className="hover:shadow-md transition-shadow">
                  <CardContent className="p-4">
                    {productImage && (
                      <img
                        src={productImage}
                        alt={productName}
                        className="w-full h-32 object-cover rounded-lg mb-3"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none'
                        }}
                      />
                    )}
                    <h3 className="font-semibold text-sm mb-1 line-clamp-2">
                      {productName}
                      {productBrand && <span className="text-xs text-muted-foreground ml-1">by {productBrand}</span>}
                    </h3>
                    {productQty && (
                      <p className="text-xs text-muted-foreground mb-2">{productQty}</p>
                    )}
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-primary">
                        {productPrice > 0 ? formatPrice(productPrice) : 'Price unavailable'}
                      </span>
                      <Button
                        size="sm"
                        variant={cart[productId]?.quantity ? "default" : "outline"}
                        onClick={() => addToCart(product, productId)}
                      >
                        {cart[productId]?.quantity ? `Add (${cart[productId].quantity})` : 'Add'}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* Empty State */}
      {products.length === 0 && searchQuery && !searching && (
        <Card>
          <CardContent className="py-12 text-center">
            <Package className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              No products found. Try a different search term.
            </p>
          </CardContent>
        </Card>
      )}

      {/* No Address State */}
      {addresses.length === 0 && !loading && (
        <Card>
          <CardContent className="py-12 text-center">
            <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              No delivery addresses found. Please add an address in your Swiggy account.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Floating Cart Summary */}
      {cartItemCount > 0 && (
        <div className="fixed bottom-6 right-6 z-50 bg-primary text-primary-foreground px-5 py-3 rounded-full shadow-2xl flex items-center gap-3">
          <ShoppingCart className="h-5 w-5" />
          <span className="font-semibold text-sm">
            Cart: {cartItemCount} item{cartItemCount > 1 ? 's' : ''} {cartTotalAmount > 0 ? `(${formatPrice(cartTotalAmount)})` : ''}
          </span>
        </div>
      )}
    </div>
  )
}
