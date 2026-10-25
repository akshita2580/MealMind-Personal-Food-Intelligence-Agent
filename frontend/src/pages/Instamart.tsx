import { useState, useEffect } from 'react'
import { MapPin, Search, ShoppingCart, Package, Plus, Minus, Trash2, X, Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getAddresses, searchProducts, getInstamartCart, updateInstamartCart, clearInstamartCart } from '@/services/api'

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
    price?: any;
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

interface CartItem {
  spinId: string;
  quantity: number;
  product?: Product;
  // For display
  name?: string;
  brand?: string;
  price?: number;
  quantity_str?: string;
  image_url?: string;
}

export default function Instamart() {
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cartLoading, setCartLoading] = useState(false)
  const [cartUpdating, setCartUpdating] = useState<string | null>(null)
  const [showCart, setShowCart] = useState(false)

  // Cart state from backend
  const [cart, setCart] = useState<CartItem[]>([])
  const [cartTotal, setCartTotal] = useState(0)

  // Load addresses on mount
  useEffect(() => {
    loadAddresses()
  }, [])

  // Load cart when address is selected
  useEffect(() => {
    if (selectedAddress) {
      loadCart()
    }
  }, [selectedAddress])

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

  const loadCart = async () => {
    if (!selectedAddress) return

    try {
      setCartLoading(true)
      const data = await getInstamartCart()
      console.log('Cart response:', data)
      if (data.success === false) {
        throw new Error(data.error?.message || 'Swiggy could not load the Instamart cart')
      }

      // Parse cart items from backend response
      const items: CartItem[] = []
      if (data.items && Array.isArray(data.items)) {
        for (const item of data.items) {
          // Extract product info from item
          const product = item.product || {}
          items.push({
            spinId: item.spinId,
            quantity: item.quantity,
            product,
            name: product.displayName || product.name || product.product_name || product.title || 'Product',
            brand: product.brand || '',
            price: product.variations?.[0]?.price?.mrp || product.variations?.[0]?.price?.offer_price || product.variations?.[0]?.mrp || product.variations?.[0]?.price || product.price || product.product_price || product.mrp || 0,
            quantity_str: product.variations?.[0]?.quantity || product.variations?.[0]?.size || product.quantity || product.pack_size || product.size || '',
            image_url: product.image_url || product.imageUrl || product.image,
          })
        }
      }

      setCart(items)
      setCartTotal(data.total || items.reduce((sum, item) => sum + (item.price || 0) * item.quantity, 0))
    } catch (err) {
      console.error('Load cart error:', err)
      setError(err instanceof Error ? err.message : 'Failed to load Instamart cart')
      // Keep the last known cart state; a failed refresh is not an empty cart.
    } finally {
      setCartLoading(false)
    }
  }

  const updateCartItem = async (spinId: string, quantity: number, product?: Product) => {
    if (!selectedAddress) return

    try {
      setCartUpdating(spinId)

      // Build items array for the API call
      const currentItems = cart.map(item => ({
        spinId: item.spinId,
        quantity: item.spinId === spinId ? quantity : item.quantity
      }))

      // If adding new item not in cart
      if (!cart.find(item => item.spinId === spinId) && product) {
        currentItems.push({ spinId, quantity })
      }

      // Filter out zero quantity items
      const itemsToSend = currentItems.filter(item => item.quantity > 0)

      const result = await updateInstamartCart(selectedAddress.id, itemsToSend)
      console.log('Update cart result:', result)
      const failure = result.cart?.error?.message || result.error?.message
      if (result.success === false || result.cart?.success === false) {
        throw new Error(failure || 'Swiggy rejected the cart update')
      }

      // Reload cart to get updated state from backend
      await loadCart()
    } catch (err) {
      console.error('Update cart error:', err)
      const errorMsg = err instanceof Error ? err.message : 'Failed to update cart'
      
      // Show user-friendly error message
      if (errorMsg.includes('getaddrinfo failed') || errorMsg.includes('Network error')) {
        setError('Cannot connect to Swiggy servers. Please check your internet connection and try again.')
      } else if (errorMsg.includes('removed the item')) {
        setError('This item is no longer available. The restaurant may have removed it from their menu.')
      } else {
        setError(errorMsg)
      }
    } finally {
      setCartUpdating(null)
    }
  }

  const handleAddToCart = (product: Product, productId: string) => {
    // Get spinId from product
    const spinId = product.spinId || product.productId || product.id || product.product_id || productId
    updateCartItem(spinId, 1, product)
  }

  const handleIncrement = (spinId: string, currentQuantity: number, product?: Product) => {
    updateCartItem(spinId, currentQuantity + 1, product)
  }

  const handleDecrement = (spinId: string, currentQuantity: number, product?: Product) => {
    if (currentQuantity <= 1) {
      updateCartItem(spinId, 0, product)
    } else {
      updateCartItem(spinId, currentQuantity - 1, product)
    }
  }

  const handleClearCart = async () => {
    if (!selectedAddress) return

    try {
      setCartLoading(true)
      await clearInstamartCart()
      setCart([])
      setCartTotal(0)
      setShowCart(false)
    } catch (err) {
      console.error('Clear cart error:', err)
      setError(err instanceof Error ? err.message : 'Failed to clear cart')
    } finally {
      setCartLoading(false)
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
      let productsList: Product[] = []
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

  const getProductPrice = (product: Product): number => {
    if (product.variations && Array.isArray(product.variations) && product.variations.length > 0) {
      const firstVariation = product.variations[0];
      return firstVariation.price?.mrp || firstVariation.price?.offer_price || firstVariation.mrp || firstVariation.price || 0;
    }
    return product.price || product.product_price || product.mrp || 0;
  }

  const getProductQty = (product: Product): string => {
    if (product.variations && Array.isArray(product.variations) && product.variations.length > 0) {
      return product.variations[0].quantity || product.variations[0].size || '';
    }
    return product.quantity || product.pack_size || product.size || '';
  }

  const getProductImage = (product: Product): string | undefined => {
    return product.image_url || product.imageUrl || product.image;
  }

  const getProductId = (product: Product, idx: number): string => {
    return product.spinId || product.productId || product.id || product.product_id || `product-${idx}`;
  }

  const cartItemCount = cart.reduce((sum, item) => sum + item.quantity, 0)

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
                {searching ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : 'Search'}
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
              const productName = product.displayName || product.name || product.product_name || product.title || 'Product';
              const productBrand = product.brand || '';
              const productPrice = getProductPrice(product);
              const productQty = getProductQty(product);
              const productImage = getProductImage(product);
              const productId = getProductId(product, idx);

              // Find matching cart item
              const cartItem = cart.find(item => item.spinId === productId)
              const inCartQuantity = cartItem?.quantity || 0
              const isUpdating = cartUpdating === productId

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
                      {inCartQuantity > 0 ? (
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDecrement(productId, inCartQuantity, product)}
                            disabled={isUpdating}
                            aria-label="Decrease quantity"
                          >
                            {isUpdating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Minus className="h-4 w-4" />}
                          </Button>
                          <span className="w-8 text-center font-medium">{inCartQuantity}</span>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleIncrement(productId, inCartQuantity, product)}
                            disabled={isUpdating}
                            aria-label="Increase quantity"
                          >
                            {isUpdating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          onClick={() => handleAddToCart(product, productId)}
                          disabled={isUpdating}
                        >
                          {isUpdating ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
                          Add
                        </Button>
                      )}
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

      {/* Cart Drawer */}
      {cartItemCount > 0 && (
        <div className="fixed inset-0 z-50" onClick={() => setShowCart(false)}>
          <div className="fixed right-0 top-0 h-full w-full max-w-md bg-background shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Cart Header */}
            <div className="flex items-center justify-between p-4 border-b">
              <h2 className="text-xl font-semibold">Your Cart</h2>
              <div className="flex items-center gap-2">
                {cartItemCount > 0 && (
                  <Button variant="ghost" size="sm" onClick={handleClearCart} disabled={cartLoading}>
                    <Trash2 className="h-4 w-4 mr-1" />
                    Clear
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => setShowCart(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Cart Items */}
            <div className="flex-1 overflow-y-auto p-4">
              {cartLoading ? (
                <div className="flex items-center justify-center h-64">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : cart.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <ShoppingCart className="h-12 w-12 mx-auto mb-4" />
                  <p>Your cart is empty</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {cart.map((item) => (
                    <div key={item.spinId} className="flex gap-3">
                      {item.image_url && (
                        <img
                          src={item.image_url}
                          alt={item.name}
                          className="w-16 h-16 object-cover rounded-lg"
                          onError={(e) => { e.currentTarget.style.display = 'none' }}
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-sm truncate">{item.name}</h4>
                        {item.brand && <p className="text-xs text-muted-foreground">{item.brand}</p>}
                        {item.quantity_str && <p className="text-xs text-muted-foreground">{item.quantity_str}</p>}
                        <p className="font-semibold text-primary mt-1">
                          {item.price && item.price > 0 ? formatPrice(item.price) : 'Price unavailable'}
                        </p>
                        <div className="flex items-center gap-2 mt-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleDecrement(item.spinId, item.quantity, item.product)}
                            disabled={cartUpdating === item.spinId}
                            aria-label="Decrease quantity"
                          >
                            <Minus className="h-4 w-4" />
                          </Button>
                          <span className="w-8 text-center font-medium">{item.quantity}</span>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleIncrement(item.spinId, item.quantity, item.product)}
                            disabled={cartUpdating === item.spinId}
                            aria-label="Increase quantity"
                          >
                            <Plus className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => updateCartItem(item.spinId, 0, item.product)}
                            disabled={cartUpdating === item.spinId}
                            className="ml-2 text-destructive hover:text-destructive"
                            aria-label="Remove item"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Cart Footer */}
            <div className="p-4 border-t bg-background/95 backdrop-blur-sm">
              <div className="flex justify-between text-lg font-semibold mb-4">
                <span>Total</span>
                <span>{formatPrice(cartTotal)}</span>
              </div>
              <Button
                className="w-full"
                size="lg"
                onClick={() => {
                  // TODO: Navigate to checkout
                  alert('Checkout functionality to be implemented')
                }}
              >
                Proceed to Checkout
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Cart Summary Button */}
      {cartItemCount > 0 && !showCart && (
        <div className="fixed bottom-6 right-6 z-50">
          <Button
            className="bg-primary text-primary-foreground px-5 py-3 rounded-full shadow-2xl flex items-center gap-3"
            onClick={() => setShowCart(true)}
          >
            <ShoppingCart className="h-5 w-5" />
            <span className="font-semibold text-sm">
              Cart: {cartItemCount} item{cartItemCount > 1 ? 's' : ''} ({formatPrice(cartTotal)})
            </span>
          </Button>
        </div>
      )}
    </div>
  )
}