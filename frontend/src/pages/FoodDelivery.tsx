import { useState, useEffect, useRef } from 'react'
import { MapPin, Search, UtensilsCrossed, ChevronRight, ArrowLeft, Plus, ShoppingCart } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getAddresses, searchRestaurants, getRestaurantMenu, searchMenu, updateFoodCart, getPaymentOptions, type FeeBreakdownItem } from '@/services/api'

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
  menu_item_id?: string;
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
  hasVariants?: boolean;
  hasAddons?: boolean;
  variations?: Array<{ id?: string; name?: string; groupId?: string; default?: number; inStock?: number }>;
  variantsV2?: Array<{ groupId?: string; name?: string; variations?: Array<{ id?: string; name?: string; default?: number; inStock?: number }> }>;
  addons?: Array<{ groupId?: string; groupName?: string; minAddons?: number; maxAddons?: number; choices?: Array<{ id?: string; name?: string; price?: number }> }>;
  selectedCartVariants?: any[];
  selectedCartVariantsV2?: any[];
  selectedCartAddons?: any[];
}

function selectSwiggyCustomizations(item: MenuItem): { variants?: any[]; variantsV2?: any[]; addons?: any[] } | null {
  const choose = (label: string, options: any[]) => {
    const available = options.filter(option => option && option.inStock !== 0)
    if (available.length === 0) throw new Error(`Swiggy has no available choices for ${label}.`)
    if (available.length === 1) return available[0]
    const lines = available.map((option, index) => `${index + 1}. ${option.name || 'Option'}${option.price != null ? ` — ₹${option.price}` : ''}`).join('\n')
    const answer = window.prompt(`${label}\n${lines}\nEnter the option number:`)
    if (answer === null) return null
    const index = Number(answer.trim()) - 1
    if (!Number.isInteger(index) || index < 0 || index >= available.length) {
      throw new Error(`Choose a valid option number for ${label}.`)
    }
    return available[index]
  }

  const selected: { variants?: any[]; variantsV2?: any[]; addons?: any[] } = {}
  if (item.variantsV2?.length) {
    selected.variantsV2 = []
    for (const group of item.variantsV2) {
      const option = choose(group.name || 'Choose an item variant', group.variations || [])
      if (option === null) return null
      selected.variantsV2.push({ ...group, variations: [option] })
    }
  } else if (item.variations?.length) {
    const option = choose('Choose an item variant', item.variations)
    if (option === null) return null
    selected.variants = [{
      id: option.id,
      name: option.name,
      groupId: option.groupId,
      group_id: option.groupId,
      variationId: option.id,
      variation_id: option.id,
      price: option.price,
    }]
  } else if (item.hasVariants) {
    throw new Error('Swiggy requires a variant, but its search response did not include the available choices. Refresh the menu and retry.')
  }

  const chosenAddons: any[] = []
  for (const group of item.addons || []) {
    const choices = (group.choices || []).filter(choice => choice && choice.id)
    const minimum = Math.max(0, Number(group.minAddons || 0))
    const maximum = Math.max(minimum, Number(group.maxAddons || choices.length))
    if (minimum === 0) continue
    const lines = choices.map((choice, index) => `${index + 1}. ${choice.name || 'Add-on'}${choice.price != null ? ` — ₹${choice.price}` : ''}`).join('\n')
    const answer = window.prompt(`${group.groupName || 'Choose required add-ons'} (select ${minimum}${maximum > minimum ? `-${maximum}` : ''}, comma-separated)\n${lines}`)
    if (answer === null) return null
    const indexes = [...new Set(answer.split(',').map(value => Number(value.trim()) - 1))]
    if (indexes.some(index => !Number.isInteger(index) || index < 0 || index >= choices.length) || indexes.length < minimum || indexes.length > maximum) {
      throw new Error(`Select between ${minimum} and ${maximum} valid add-ons for ${group.groupName || 'this item'}.`)
    }
    chosenAddons.push(...indexes.map(index => ({
      ...choices[index],
      groupId: group.groupId,
      group_id: group.groupId,
      quantity: 1,
    })))
  }
  if (item.hasAddons && !item.addons?.length) {
    throw new Error('Swiggy requires add-on details for this dish but did not return them. Refresh the menu and retry.')
  }
  if (chosenAddons.length) selected.addons = chosenAddons
  return selected
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
  const [moreMenuCategories, setMoreMenuCategories] = useState<string[]>([])
  const [loadingMoreCategory, setLoadingMoreCategory] = useState<string | null>(null)
  const [loadingMenu, setLoadingMenu] = useState(false)

  // Cart state
  const [cart, setCart] = useState<Record<string, { item: MenuItem; quantity: number }>>({})
  const cartRef = useRef(cart)
  const [cartRestaurantId, setCartRestaurantId] = useState<string | null>(null)
  const [cartOpen, setCartOpen] = useState(false)
  const [cartSyncError, setCartSyncError] = useState<string | null>(null)
  const [cartSyncing, setCartSyncing] = useState(false)
  const pendingCartOperations = useRef(0)
  const cartSyncQueue = useRef<Promise<unknown>>(Promise.resolve())

  // Checkout state
  const [checkoutOpen, setCheckoutOpen] = useState(false)
  const [checkoutLoading, setCheckoutLoading] = useState(false)
  const [checkoutBreakdown, setCheckoutBreakdown] = useState<FeeBreakdownItem[]>([])
  const [checkoutGrandTotal, setCheckoutGrandTotal] = useState<number | null>(null)
  const [checkoutItemTotal, setCheckoutItemTotal] = useState<number | null>(null)
  const [checkoutBreakdownAvailable, setCheckoutBreakdownAvailable] = useState(false)
  const [checkoutMethods, setCheckoutMethods] = useState<string[]>([])
  const [checkoutError, setCheckoutError] = useState<string | null>(null)

  const commitCart = (nextCart: Record<string, { item: MenuItem; quantity: number }>) => {
    cartRef.current = nextCart
    setCart(nextCart)
  }

  const beginCartOperation = () => {
    pendingCartOperations.current += 1
    setCartSyncing(true)
  }

  const finishCartOperation = () => {
    pendingCartOperations.current = Math.max(0, pendingCartOperations.current - 1)
    if (pendingCartOperations.current === 0) setCartSyncing(false)
  }

  const syncCartSnapshot = async (
    nextCart: Record<string, { item: MenuItem; quantity: number }>,
    addressId = selectedAddress?.id,
    restaurantId = cartRestaurantId || selectedRestaurant?.id,
  ) => {
    if (!addressId || !restaurantId) return
    const items = Object.entries(nextCart).map(([itemKey, entry]) => {
      const menuItemId = entry.item.menu_item_id
      if (!menuItemId) throw new Error(`“${entry.item.name || entry.item.item_name || itemKey}” has no Swiggy menu item ID and cannot be synced.`)
      return {
        menu_item_id: String(menuItemId),
        quantity: entry.quantity,
        ...(entry.item.selectedCartVariants ? { variants: entry.item.selectedCartVariants } : {}),
        ...(entry.item.selectedCartVariantsV2 ? { variantsV2: entry.item.selectedCartVariantsV2 } : {}),
        ...(entry.item.selectedCartAddons ? { addons: entry.item.selectedCartAddons } : {}),
      }
    })
    // #region agent log
    fetch('http://127.0.0.1:7268/ingest/7217c377-b554-47f6-b4c0-f0d452589dcd',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'dad6f0'},body:JSON.stringify({sessionId:'dad6f0',hypothesisId:'H2',location:'FoodDelivery.tsx:syncCartSnapshot',message:'cart payload to /food/cart',data:{restaurantId,itemCount:items.length,items:items.map(i=>({menu_item_id:i.menu_item_id,quantity:i.quantity,variantKeys:i.variants?Object.keys(i.variants[0]||{}):[],variantsV2Keys:i.variantsV2?Object.keys(i.variantsV2[0]||{}):[],addonKeys:i.addons?Object.keys(i.addons[0]||{}):[],variantsV2Sample:i.variantsV2?.[0]||null}))},timestamp:Date.now(),runId:'pre-fix'})}).catch(()=>{});
    // #endregion

    beginCartOperation()
    const queuedSync = cartSyncQueue.current.catch(() => undefined).then(() => updateFoodCart(addressId, restaurantId, items))
    cartSyncQueue.current = queuedSync
    try {
      await queuedSync
      setCartSyncError(null)
    } catch (err) {
      setCartSyncError(err instanceof Error ? err.message : 'Could not sync the full cart to Swiggy')
      throw err
    } finally {
      finishCartOperation()
    }
  }

  const addToCart = async (item: MenuItem) => {
    if (!selectedAddress || !selectedRestaurant) return
    setCartSyncError(null)
    if (cartRestaurantId && cartRestaurantId !== selectedRestaurant.id && Object.keys(cartRef.current).length > 0) {
      setCartSyncError('Swiggy allows items from one restaurant per cart. Remove the current items before choosing another restaurant.')
      return
    }

    const itemName = item.name || item.item_name || 'Item'
    let orderableItem = item
    beginCartOperation()
    try {
      // #region agent log
      fetch('http://127.0.0.1:7268/ingest/7217c377-b554-47f6-b4c0-f0d452589dcd',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'dad6f0'},body:JSON.stringify({sessionId:'dad6f0',hypothesisId:'H1',location:'FoodDelivery.tsx:addToCart',message:'compact menu item before resolve',data:{restaurantId:selectedRestaurant.id,name:itemName,id:item.id,menu_item_id:item.menu_item_id,item_id:item.item_id,hasVariants:item.hasVariants,hasAddons:item.hasAddons,variationsLen:item.variations?.length||0,variantsV2Len:item.variantsV2?.length||0,addonsLen:item.addons?.length||0,willSearch:!item.menu_item_id||item.hasVariants||item.hasAddons||!!item.variations?.length||!!item.variantsV2?.length||!!item.addons?.length},timestamp:Date.now(),runId:'pre-fix'})}).catch(()=>{});
      // #endregion
      // The compact restaurant menu's `id` is not the orderable menu_item_id.
      // Resolve the full item through search_menu before sending it to the cart.
      if (!item.menu_item_id || item.hasVariants || item.hasAddons || item.variations?.length || item.variantsV2?.length || item.addons?.length) {
        const response = await searchMenu(selectedAddress.id, itemName, selectedRestaurant.id)
        let payload = response
        for (let depth = 0; depth < 4 && payload && typeof payload === 'object' && !Array.isArray(payload.items); depth += 1) {
          payload = payload.data || payload.result
        }
        const results = Array.isArray(payload?.items) ? payload.items : []
        const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '')
        const match = results.find((candidate: MenuItem) => normalize(candidate.name || candidate.item_name || '') === normalize(itemName))
        if (!match?.menu_item_id) {
          throw new Error(`Swiggy did not return an orderable menu_item_id for “${itemName}”. Refresh the menu and retry.`)
        }
        orderableItem = { ...item, ...match, id: match.menu_item_id }
        // #region agent log
        fetch('http://127.0.0.1:7268/ingest/7217c377-b554-47f6-b4c0-f0d452589dcd',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'dad6f0'},body:JSON.stringify({sessionId:'dad6f0',hypothesisId:'H1',location:'FoodDelivery.tsx:addToCart:search_menu',message:'search_menu match ids',data:{resultCount:results.length,match:{id:match.id,menu_item_id:match.menu_item_id,item_id:match.item_id,hasVariants:match.hasVariants,hasAddons:match.hasAddons,variationsLen:match.variations?.length||0,variantsV2Len:match.variantsV2?.length||0,variantV2Sample:match.variantsV2?.[0]?{keys:Object.keys(match.variantsV2[0]),groupId:match.variantsV2[0].groupId,name:match.variantsV2[0].name}:null}},timestamp:Date.now(),runId:'pre-fix'})}).catch(()=>{});
        // #endregion
      }
      const customizations = selectSwiggyCustomizations(orderableItem)
      if (customizations === null) {
        finishCartOperation()
        return
      }
      orderableItem = {
        ...orderableItem,
        selectedCartVariants: customizations.variants,
        selectedCartVariantsV2: customizations.variantsV2,
        selectedCartAddons: customizations.addons,
      }

    } catch (err) {
      setCartSyncError(err instanceof Error ? err.message : 'Could not resolve this dish in Swiggy’s orderable menu')
      finishCartOperation()
      return
    }

    const itemId = orderableItem.menu_item_id!
    const currentCart = cartRef.current
    const newQty = (currentCart[itemId]?.quantity || 0) + 1
    const nextCart = {
      ...currentCart,
      [itemId]: {
        item: orderableItem,
        quantity: newQty,
      }
    }
    try {
      await syncCartSnapshot(nextCart, selectedAddress.id, selectedRestaurant.id)
      // Only show the dish as added once Swiggy has confirmed it.
      commitCart(nextCart)
      setCartRestaurantId(selectedRestaurant.id)
    } catch { /* The sync error is shown in the cart panel. */ }
    finally { finishCartOperation() }
  }

  const retryCartSync = async () => {
    if (!selectedAddress || !cartRestaurantId) return
    try {
      await syncCartSnapshot(cartRef.current, selectedAddress.id, cartRestaurantId)
    } catch { /* The sync error is shown in the cart panel. */ }
  }

  const changeCartQuantity = async (itemId: string, item: MenuItem, quantity: number) => {
    const currentCart = cartRef.current
    const nextCart = { ...currentCart }
    if (quantity <= 0) delete nextCart[itemId]
    else nextCart[itemId] = { item, quantity }
    try {
      await syncCartSnapshot(nextCart)
      commitCart(nextCart)
    } catch { /* The sync error is shown in the cart panel. */ }
  }

  const handleCheckout = async () => {
    if (!selectedAddress || !cartRestaurantId || cartSyncing || Object.keys(cart).length === 0) return
    setCheckoutLoading(true)
    setCheckoutError(null)
    setCheckoutBreakdown([])
    setCheckoutGrandTotal(null)
    setCheckoutItemTotal(null)
    setCheckoutBreakdownAvailable(false)
    setCheckoutMethods([])

    try {
      const items = Object.entries(cartRef.current).map(([itemKey, entry]) => {
        const menuItemId = entry.item.menu_item_id
        if (!menuItemId) throw new Error(`“${entry.item.name || entry.item.item_name || itemKey}” has no Swiggy menu item ID and cannot be synced.`)
        return {
          menu_item_id: String(menuItemId),
          quantity: entry.quantity,
          ...(entry.item.selectedCartVariants ? { variants: entry.item.selectedCartVariants } : {}),
          ...(entry.item.selectedCartVariantsV2 ? { variantsV2: entry.item.selectedCartVariantsV2 } : {}),
          ...(entry.item.selectedCartAddons ? { addons: entry.item.selectedCartAddons } : {}),
        }
      })
      const data = await getPaymentOptions(selectedAddress.id, cartRestaurantId, items)
      setCartSyncError(null)
      setCheckoutBreakdown(data.breakdown || [])
      setCheckoutGrandTotal(data.grand_total)
      setCheckoutItemTotal(data.item_total ?? null)
      setCheckoutBreakdownAvailable(Boolean(data.breakdown_available))
      setCheckoutMethods(data.payment_methods || [])
    } catch (err) {
      // Even if the API fails, show the locally-computed total
      setCheckoutError(err instanceof Error ? err.message : 'Could not load fee breakdown from Swiggy')
    } finally {
      setCheckoutLoading(false)
      setCartOpen(false)
      setCheckoutOpen(true)
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
      
      const firstPage = await getRestaurantMenu(restaurant.id, selectedAddress.id, 1, 8)
      let menu = firstPage
      if (Array.isArray(firstPage?.categories) && firstPage.hasMore) {
        const categories = [...firstPage.categories]
        const pageSize = Number(firstPage.pageSize) || 8
        const totalPages = Number(firstPage.totalPages) || (firstPage.totalCategories
          ? Math.ceil(Number(firstPage.totalCategories) / pageSize)
          : 100)
        let page = 1
        let currentPage = firstPage

        while (currentPage.hasMore && page < Math.min(totalPages, 100)) {
          page += 1
          currentPage = await getRestaurantMenu(restaurant.id, selectedAddress.id, page, pageSize)
          const nextCategories = Array.isArray(currentPage?.categories) ? currentPage.categories : []
          if (nextCategories.length === 0) break
          categories.push(...nextCategories)
        }
        menu = { ...firstPage, categories }
      }
      console.log('=== MENU DATA DEBUG ===')
      console.log('Menu data:', menu)
      console.log('Menu type:', typeof menu)
      console.log('Menu keys:', Object.keys(menu || {}))
      
      // Parse menu items - handles multiple possible structures
      let items: MenuItem[] = []
      let categoriesForMore: any[] = []
      
      if (Array.isArray(menu)) {
        console.log('Menu is array with', menu.length, 'items')
        items = menu
      } else if (menu && typeof menu === 'object') {
        // Check various possible structures
        
        // Pattern 1: {categories: [{items: [...]}]}
        if (menu.categories && Array.isArray(menu.categories)) {
          console.log('Found categories:', menu.categories.length)
          categoriesForMore = menu.categories
        }
        // Pattern 2: {items: [...]}
        else if (menu.items && Array.isArray(menu.items)) {
          console.log('Found items array:', menu.items.length)
          items = menu.items
        }
        // Pattern 3: {menu: [...]}
        else if (menu.menu && Array.isArray(menu.menu)) {
          console.log('Found menu array:', menu.menu.length)
          items = menu.menu
        }
        // Pattern 4: {data: {categories: [...]}}
        else if (menu.data && typeof menu.data === 'object') {
          console.log('Found nested data object')
          if (menu.data.categories && Array.isArray(menu.data.categories)) {
            categoriesForMore = menu.data.categories
          } else if (menu.data.items && Array.isArray(menu.data.items)) {
            items = menu.data.items
          }
        }
        // Pattern 5: {cards: [{...}]} (Swiggy's card-based structure)
        else if (menu.cards && Array.isArray(menu.cards)) {
          console.log('Found cards array:', menu.cards.length)
          // Extract items from cards
          items = menu.cards.flatMap((card: any) => {
            if (card.groupedCard?.cardGroupMap?.REGULAR?.cards) {
              return card.groupedCard.cardGroupMap.REGULAR.cards.flatMap((c: any) =>
                c.card?.card?.itemCards?.map((ic: any) => ic.card?.info) || []
              )
            }
            return []
          }).filter(Boolean)
        }
      }

      if (categoriesForMore.length) {
        const sections = categoriesForMore.flatMap((category: any) => [
          category,
          ...(Array.isArray(category.subcategories) ? category.subcategories : []),
        ])
        items = sections.flatMap((section: any) => {
          const sectionItems = section.items || section.itemCards || section.dishes || []
          const title = section.title || section.name || section.categoryName || 'Menu'
          console.log(`Category "${title}" has ${sectionItems.length} items`)
          return sectionItems.map((item: MenuItem) => ({ ...item, category: title }))
        })
        setMoreMenuCategories([...new Set(sections
          .filter((section: any) => section.hasMoreItems || Number(section.totalItems) > (section.items || []).length)
          .map((section: any) => section.title || section.name || section.categoryName)
          .filter(Boolean))])
      } else {
        setMoreMenuCategories([])
      }

      console.log('=== EXTRACTED MENU ITEMS ===')
      console.log('Total items extracted:', items.length)
      if (items.length > 0) {
        console.log('First item:', items[0])
        console.log('First item keys:', Object.keys(items[0] || {}))
      }
      
      setMenuItems(items)
    } catch (err) {
      console.error('Menu load error:', err)
      setError(err instanceof Error ? err.message : 'Failed to load menu')
      setMenuItems([])
      setMoreMenuCategories([])
    } finally {
      setLoadingMenu(false)
    }
  }
  
  const handleBackToSearch = () => {
    setSelectedRestaurant(null)
    setMenuItems([])
    setMoreMenuCategories([])
  }

  const loadRemainingCategoryItems = async (categoryName: string) => {
    if (!selectedAddress || !selectedRestaurant) return
    setLoadingMoreCategory(categoryName)
    setError(null)
    try {
      let offset = 0
      let hasMore = true
      const loaded: MenuItem[] = []
      let pages = 0
      while (hasMore && pages < 50) {
        const response = await searchMenu(selectedAddress.id, categoryName, selectedRestaurant.id, offset)
        const payload = response?.data && typeof response.data === 'object' ? response.data : response
        const pageItems = Array.isArray(payload?.items) ? payload.items : []
        loaded.push(...pageItems.map((item: MenuItem) => ({ ...item, category: categoryName })))
        hasMore = Boolean(payload?.hasMore)
        const nextOffset = Number(payload?.nextOffset)
        if (!hasMore || pageItems.length === 0 || !Number.isFinite(nextOffset) || nextOffset <= offset) break
        offset = nextOffset
        pages += 1
      }
      setMenuItems(current => {
        const existing = new Set(current.map(item => item.menu_item_id || item.item_id || item.id || item.name))
        const additions: MenuItem[] = []
        for (const item of loaded) {
          const id = item.menu_item_id || item.item_id || item.id || item.name
          if (id && !existing.has(id)) {
            existing.add(id)
            additions.push(item)
          }
        }
        return [...current, ...additions]
      })
      if (loaded.length > 0) {
        setMoreMenuCategories(current => current.filter(name => name !== categoryName))
      } else {
        setError(`Swiggy did not return more dishes for “${categoryName}”. Try searching for a dish by name.`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not load more dishes from ${categoryName}`)
    } finally {
      setLoadingMoreCategory(null)
    }
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
              <h2 className="text-xl font-semibold mb-4">Menu ({menuItems.length} items)</h2>
              <div className="grid gap-4">
                {menuItems.map((item, idx) => {
                  const itemName = item.name || item.item_name || 'Item';
                  const itemPrice = item.price || item.item_price || 0;
                  const itemDesc = item.description || item.item_description || '';
                  const itemImage = item.image_url || item.imageUrl || item.image;
                  const itemId = item.menu_item_id || item.item_id || item.id || `item-${idx}`;
                  // Use combination of ID and index to ensure uniqueness
                  const uniqueKey = `${itemId}-${idx}`;
                  const normalizedName = (item.name || item.item_name || '').toLowerCase().replace(/[^a-z0-9]/g, '')
                  const quantityInCart = Object.values(cart).find(({ item: cartItem }) =>
                    (item.menu_item_id && cartItem.menu_item_id === item.menu_item_id) ||
                    (item.id && (cartItem.id === item.id || cartItem.menu_item_id === item.id)) ||
                    normalizedName === (cartItem.name || cartItem.item_name || '').toLowerCase().replace(/[^a-z0-9]/g, '')
                  )?.quantity || 0;
                  
                  return (
                    <Card key={uniqueKey}>
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
              {moreMenuCategories.length > 0 && (
                <Card className="mt-4">
                  <CardContent className="p-4 space-y-3">
                    <p className="text-sm text-muted-foreground">
                      Swiggy limits menu browsing to 10 dishes per category. Search Swiggy for additional dishes in a category:
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {moreMenuCategories.map(category => (
                        <Button
                          key={category}
                          variant="outline"
                          onClick={() => loadRemainingCategoryItems(category)}
                          disabled={loadingMoreCategory !== null}
                        >
                          {loadingMoreCategory === category ? `Loading ${category}…` : `More ${category}`}
                        </Button>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                {error ? (
                  <div className="space-y-3">
                    <p className="text-destructive">{error}</p>
                    <Button
                      variant="outline"
                      onClick={() => handleRestaurantClick(selectedRestaurant)}
                      disabled={loadingMenu}
                    >
                      Retry loading menu
                    </Button>
                  </div>
                ) : (
                  <p className="text-muted-foreground">This restaurant has no menu available through Swiggy right now.</p>
                )}
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

      {/* Floating Cart Button */}
      {cartItemCount > 0 && (
        <button
          onClick={() => setCartOpen(true)}
          className="fixed bottom-6 right-6 z-50 bg-primary text-primary-foreground px-5 py-3 rounded-full shadow-2xl flex items-center gap-3 hover:opacity-90 active:scale-95 transition-all"
        >
          <ShoppingCart className="h-5 w-5" />
          <span className="font-semibold text-sm">
            Cart: {cartItemCount} item{cartItemCount > 1 ? 's' : ''} ({formatPrice(cartTotalAmount)})
          </span>
        </button>
      )}

      {cartSyncError && !cartOpen && !checkoutOpen && (
        <div className="fixed bottom-20 right-6 z-50 max-w-sm rounded-md border border-destructive/30 bg-background p-3 text-sm text-destructive shadow-lg">
          Swiggy cart sync failed: {cartSyncError}
        </div>
      )}

      {/* Cart Drawer */}
      {cartOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setCartOpen(false)}
          />
          {/* Panel */}
          <div className="relative w-full max-w-sm bg-background shadow-2xl flex flex-col h-full">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <ShoppingCart className="h-5 w-5 text-primary" />
                Your Cart
              </h2>
              <button
                onClick={() => setCartOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors text-2xl leading-none"
                aria-label="Close cart"
              >
                ✕
              </button>
            </div>

            {/* Items */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
              {cartSyncError && (
                <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                  <p>Swiggy could not confirm the cart update: {cartSyncError}</p>
                  <Button className="mt-2" size="sm" variant="outline" onClick={retryCartSync} disabled={cartSyncing}>
                    {cartSyncing ? 'Syncing…' : 'Retry sync'}
                  </Button>
                </div>
              )}
              {cartItemsList.length === 0 ? (
                <p className="text-muted-foreground text-center py-12">Your cart is empty.</p>
              ) : (
                cartItemsList.map(({ item, quantity }) => {
                  const itemName = item.name || item.item_name || 'Item'
                  const itemPrice = item.price || item.item_price || 0
                  const itemId = item.menu_item_id || item.item_id || item.id || `item-${itemName}`
                  return (
                    <div key={itemId} className="flex items-center gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">{itemName}</p>
                        <p className="text-sm text-muted-foreground">
                          {itemPrice > 0 ? formatPrice(itemPrice) : 'Price on request'} × {quantity}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          className="w-7 h-7 rounded-full border flex items-center justify-center text-lg leading-none hover:bg-muted transition-colors"
                          onClick={() => {
                            void changeCartQuantity(itemId, item, quantity - 1)
                          }}
                        >
                          −
                        </button>
                        <span className="font-semibold w-4 text-center">{quantity}</span>
                        <button
                          className="w-7 h-7 rounded-full border flex items-center justify-center text-lg leading-none hover:bg-muted transition-colors"
                          onClick={() => {
                            void changeCartQuantity(itemId, item, quantity + 1)
                          }}
                        >
                          +
                        </button>
                      </div>
                      <span className="font-semibold text-sm shrink-0 w-20 text-right">
                        {itemPrice > 0 ? formatPrice(itemPrice * quantity) : '—'}
                      </span>
                    </div>
                  )
                })
              )}
            </div>

            {/* Footer */}
            {cartItemsList.length > 0 && (
              <div className="border-t px-5 py-4 space-y-3">
                <div className="flex justify-between font-bold text-lg">
                  <span>Subtotal</span>
                  <span>{formatPrice(cartTotalAmount)}</span>
                </div>
                <Button
                  className="w-full"
                  size="lg"
                  onClick={handleCheckout}
                  disabled={checkoutLoading || cartSyncing}
                >
                  {cartSyncing ? 'Syncing cart to Swiggy…' : checkoutLoading ? 'Loading bill…' : 'Proceed to Checkout →'}
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Checkout Panel */}
      {checkoutOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40" onClick={() => setCheckoutOpen(false)} />

          {/* Panel */}
          <div className="relative w-full max-w-sm bg-background shadow-2xl flex flex-col h-full">

            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b">
              <button
                className="text-muted-foreground hover:text-foreground transition-colors mr-3"
                onClick={() => { setCheckoutOpen(false); setCartOpen(true) }}
                aria-label="Back to cart"
              >
                ← Cart
              </button>
              <h2 className="text-xl font-bold flex-1">Checkout</h2>
              <button
                onClick={() => setCheckoutOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors text-2xl leading-none"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">

              {/* Order items summary */}
              <section>
                <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">
                  Your Order
                </h3>
                <div className="space-y-2">
                  {cartItemsList.map(({ item, quantity }) => {
                    const name = item.name || item.item_name || 'Item'
                    const price = item.price || item.item_price || 0
                    const id = item.menu_item_id || item.item_id || item.id || `item-${name}`
                    return (
                      <div key={id} className="flex justify-between text-sm">
                        <span>{name} × {quantity}</span>
                        <span className="font-medium">
                          {price > 0 ? formatPrice(price * quantity) : '—'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </section>

              {/* Fee breakdown from Swiggy */}
              <section>
                <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">
                  Bill Details
                </h3>

                {checkoutError && (
                  <p className="text-xs text-amber-600 bg-amber-50 rounded px-3 py-2 mb-3">
                    ⚠ {checkoutError} — showing local subtotal only.
                  </p>
                )}
                  {!checkoutError && !checkoutBreakdownAvailable && (
                    <p className="text-xs text-amber-600 bg-amber-50 rounded px-3 py-2 mb-3">
                      Swiggy has not returned the live bill details yet. The amount below is the item subtotal only.
                    </p>
                  )}

                <div className="space-y-2">
                  {/* Always show item subtotal */}
                  <div className="flex justify-between text-sm">
                    <span>Item total</span>
                    <span>{formatPrice(checkoutItemTotal ?? cartTotalAmount)}</span>
                  </div>

                  {/* Breakdown rows from Swiggy (delivery fee, GST, surge, discount…) */}
                  {checkoutBreakdown.map((row, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-muted-foreground">{row.label}</span>
                      <span className={row.amount < 0 ? 'text-green-600 font-medium' : ''}>
                        {row.amount < 0
                          ? `− ${formatPrice(Math.abs(row.amount))}`
                          : formatPrice(row.amount)}
                      </span>
                    </div>
                  ))}

                  <div className="border-t pt-2 flex justify-between font-bold text-base">
                    <span>To Pay</span>
                    <span>
                      {checkoutGrandTotal !== null
                        ? formatPrice(checkoutGrandTotal)
                        : 'Awaiting Swiggy bill'}
                    </span>
                  </div>
                </div>
              </section>

              {/* Payment method */}
              {checkoutMethods.length > 0 && (
                <section>
                  <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-3">
                    Pay With
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {checkoutMethods.map((m) => (
                      <span key={m} className="text-sm border rounded-full px-3 py-1 bg-secondary">
                        {m}
                      </span>
                    ))}
                  </div>
                </section>
              )}

              {/* Delivery address */}
              {selectedAddress && (
                <section>
                  <h3 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide mb-2">
                    Delivering To
                  </h3>
                  <p className="text-sm">{selectedAddress.addressLine}</p>
                  {selectedAddress.addressTag && (
                    <span className="inline-block mt-1 text-xs bg-secondary px-2 py-1 rounded">
                      {selectedAddress.addressTag}
                    </span>
                  )}
                </section>
              )}
            </div>

            {/* Place Order footer */}
            <div className="border-t px-5 py-4 space-y-3">
              <div className="flex justify-between font-bold text-lg">
                <span>Total</span>
                <span>
                  {checkoutGrandTotal !== null
                    ? formatPrice(checkoutGrandTotal)
                    : 'Awaiting Swiggy bill'}
                </span>
              </div>
              <Button className="w-full" size="lg" disabled={checkoutLoading || checkoutError !== null || checkoutGrandTotal === null}>
                {checkoutGrandTotal === null ? 'Waiting for Swiggy bill' : 'Place Order'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
