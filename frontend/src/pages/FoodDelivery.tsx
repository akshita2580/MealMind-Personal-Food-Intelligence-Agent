import { useState, useEffect } from 'react'
import { MapPin, Search, UtensilsCrossed, ChevronRight, ArrowLeft, Plus, ShoppingCart } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getAddresses, searchRestaurants, getRestaurantMenu, updateFoodCart } from '@/services/api'

interface Address {
  id: string;
  addressLine: string;
  addressCategory?: string;
  addressTag?: string;
  phoneNumber?: string;
}

interface Restaurant {
  id: string;
  name: string;
  cuisine: string[];
  rating: number;
  delivery_time: string;
  cost_for_two: string;
  image_url?: string;
}

interface MenuItem {
  id?: string;
  item_id?: string;
  name?: string;
  item_name?: string;
  description?: string;
  item_description?: string;
  price?: number;
  item_price?: number;
  image_url?: string;
  imageUrl?: string;
  image?: string;
  is_veg?: boolean;
  category?: string;
}

export default function FoodDelivery() {
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // Menu viewing state
  const [selectedRestaurant, setSelectedRestaurant] = useState<Restaurant | null>(null)
  const [menuItems, setMenuItems] = useState<MenuItem[]>([])
  const [loadingMenu, setLoadingMenu] = useState(false)

  // Cart state
  const [cart, setCart] = useState<Record<string, { item: MenuItem; quantity: number }>>({})

  const addToCart = async (item: MenuItem) => {
    const itemName = item.name || item.item_name || 'Item'
    const itemId = item.id || item.item_id || `item-${itemName}`
    const newQty = (cart[itemId]?.quantity || 0) + 1

    setCart(prev => ({
      ...prev,
      [itemId]: {
        item,
        quantity: newQty,
      }
    }))

    if (selectedAddress && selectedRestaurant) {
      try {
        await updateFoodCart(selectedAddress.id, selectedRestaurant.id, itemId, newQty)
      } catch (err) {
        console.warn('Backend food cart update:', err)
      }
    }
  }

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
      const data = await searchRestaurants(selectedAddress.id, searchQuery)
      console.log('Search results:', data)
      
      // Parse the response - it might be in different formats
      let restaurantsList = []
      if (Array.isArray(data)) {
        restaurantsList = data
      } else if (data.restaurants) {
        restaurantsList = data.restaurants
      }
      
      console.log('Parsed restaurants:', restaurantsList)
      setRestaurants(restaurantsList)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed')
      setRestaurants([])
    } finally {
      setSearching(false)
    }
  }
  
  const handleRestaurantClick = async (restaurant: Restaurant) => {
    if (!selectedAddress) return
    
    try {
      setSelectedRestaurant(restaurant)
      setLoadingMenu(true)
      setError(null)
      
      const menu = await getRestaurantMenu(restaurant.id, selectedAddress.id)
      console.log('Menu data:', menu)
      
      // Parse menu items - handles Array, categories (Swiggy MCP), items, or menu
      let items: MenuItem[] = []
      if (Array.isArray(menu)) {
        items = menu
      } else if (menu?.categories && Array.isArray(menu.categories)) {
        // Swiggy MCP returns menus grouped under menu.categories where each category has items
        items = menu.categories.flatMap((cat: any) => cat.items || cat.itemCards || [])
      } else if (menu?.items && Array.isArray(menu.items)) {
        items = menu.items
      } else if (menu?.menu && Array.isArray(menu.menu)) {
        items = menu.menu
      }
      
      setMenuItems(items)
    } catch (err) {
      console.error('Menu load error:', err)
      setError(err instanceof Error ? err.message : 'Failed to load menu')
      setMenuItems([])
    } finally {
      setLoadingMenu(false)
    }
  }
  
  const handleBackToSearch = () => {
    setSelectedRestaurant(null)
    setMenuItems([])
  }
  
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(price)
  }

  const cartItemsList = Object.values(cart)
  const cartItemCount = cartItemsList.reduce((sum, ci) => sum + ci.quantity, 0)
  const cartTotalAmount = cartItemsList.reduce((sum, ci) => {
    const price = ci.item.price || ci.item.item_price || 0
    return sum + (price * ci.quantity)
  }, 0)

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

  if (error && addresses.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Card className="max-w-md">
          <CardHeader>
            <CardTitle className="text-destructive">Error</CardTitle>
            <CardDescription>{error}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={loadAddresses}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <UtensilsCrossed className="h-8 w-8 text-primary" />
          Food Delivery
        </h1>
        <p className="text-muted-foreground mt-1">
          Order from your favorite restaurants
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
            <CardTitle className="text-lg">Search Restaurants</CardTitle>
            <CardDescription>
              Find restaurants by name, cuisine, or dish
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search for restaurants, cuisines, or dishes..."
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
      {error && addresses.length > 0 && (
        <Card className="border-destructive">
          <CardContent className="py-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Search Results or Menu View */}
      {selectedRestaurant ? (
        // Menu View
        <div className="space-y-4">
          <Button onClick={handleBackToSearch} variant="outline">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Search
          </Button>
          
          <Card>
            <CardHeader>
              <CardTitle className="text-2xl">{selectedRestaurant.name}</CardTitle>
              <CardDescription>
                {(Array.isArray(selectedRestaurant.cuisine) ? selectedRestaurant.cuisine.join(', ') : (selectedRestaurant.cuisine || 'Various'))}
                {selectedRestaurant.rating ? ` • ${selectedRestaurant.rating} ⭐` : ''}
                {selectedRestaurant.delivery_time ? ` • ${selectedRestaurant.delivery_time}` : ''}
              </CardDescription>
            </CardHeader>
          </Card>
          
          {loadingMenu ? (
            <Card>
              <CardContent className="py-12 text-center">
                <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-primary mx-auto mb-4"></div>
                <p className="text-muted-foreground">Loading menu...</p>
              </CardContent>
            </Card>
          ) : menuItems.length > 0 ? (
            <div>
              <h2 className="text-xl font-semibold mb-4">Menu</h2>
              <div className="grid gap-4">
                {menuItems.map((item) => {
                  const itemName = item.name || item.item_name || 'Item';
                  const itemPrice = item.price || item.item_price || 0;
                  const itemDesc = item.description || item.item_description || '';
                  const itemImage = item.image_url || item.imageUrl || item.image;
                  const itemId = item.id || item.item_id || `item-${itemName}`;
                  const quantityInCart = cart[itemId]?.quantity || 0;
                  
                  return (
                    <Card key={itemId}>
                      <CardContent className="p-4">
                        <div className="flex gap-4">
                          {itemImage && (
                            <img
                              src={itemImage}
                              alt={itemName}
                              className="w-24 h-24 object-cover rounded-lg"
                              onError={(e) => e.currentTarget.style.display = 'none'}
                            />
                          )}
                          <div className="flex-1">
                            <div className="flex items-start justify-between">
                              <div>
                                <h3 className="font-semibold">{itemName}</h3>
                                {itemDesc && (
                                  <p className="text-sm text-muted-foreground mt-1">{itemDesc}</p>
                                )}
                              </div>
                              {item.is_veg !== undefined && (
                                <span className={`text-xs px-2 py-1 rounded ${item.is_veg ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                                  {item.is_veg ? '🌱 Veg' : '🍖 Non-veg'}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between mt-3">
                              <span className="font-bold text-lg">
                                {itemPrice > 0 ? formatPrice(itemPrice) : 'Price on request'}
                              </span>
                              <Button size="sm" onClick={() => addToCart(item)}>
                                <Plus className="h-4 w-4 mr-1" />
                                {quantityInCart > 0 ? `Add (${quantityInCart})` : 'Add'}
                              </Button>
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">Menu not available</p>
              </CardContent>
            </Card>
          )}
        </div>
      ) : (
        // Restaurant Search Results
        restaurants.length > 0 && (
          <div>
            <h2 className="text-xl font-semibold mb-4">
              Found {restaurants.length} restaurant{restaurants.length > 1 ? 's' : ''}
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              {restaurants.map((restaurant) => (
                <Card 
                  key={restaurant.id} 
                  className="hover:shadow-md transition-shadow cursor-pointer"
                  onClick={() => handleRestaurantClick(restaurant)}
                >
                  <CardContent className="p-4">
                    <div className="flex gap-4">
                      {restaurant.image_url && (
                        <div className="flex-shrink-0">
                          <img
                            src={restaurant.image_url}
                            alt={restaurant.name}
                            className="w-20 h-20 object-cover rounded-lg"
                          />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <h3 className="font-semibold text-lg truncate">{restaurant.name}</h3>
                        {restaurant.cuisine && (
                          <p className="text-sm text-muted-foreground truncate">
                            {Array.isArray(restaurant.cuisine) ? restaurant.cuisine.join(', ') : (restaurant.cuisine || 'Various')}
                          </p>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-sm">
                          {restaurant.rating && (
                            <span className="font-medium">⭐ {restaurant.rating}</span>
                          )}
                          {restaurant.delivery_time && (
                            <span className="text-muted-foreground">{restaurant.delivery_time}</span>
                          )}
                          {restaurant.cost_for_two && (
                            <span className="text-muted-foreground">{restaurant.cost_for_two}</span>
                          )}
                        </div>
                      </div>
                      <ChevronRight className="h-5 w-5 text-muted-foreground flex-shrink-0" />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )
      )}

      {/* Empty State */}
      {restaurants.length === 0 && searchQuery && !searching && (
        <Card>
          <CardContent className="py-12 text-center">
            <Search className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              No restaurants found. Try a different search term.
            </p>
          </CardContent>
        </Card>
      )}

      {/* No Address State */}
      {addresses.length === 0 && !loading && (
        <Card>
          <CardContent className="py-12 text-center">
            <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground mb-4">
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
            Cart: {cartItemCount} item{cartItemCount > 1 ? 's' : ''} ({formatPrice(cartTotalAmount)})
          </span>
        </div>
      )}
    </div>
  )
}
