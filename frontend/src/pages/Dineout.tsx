import { useState, useEffect } from 'react'
import { MapPin, Search, UtensilsCrossed, Clock, Users } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getAddresses, searchVenues } from '@/services/api'

interface Address {
  id: string;
  addressLine: string;
  addressCategory?: string;
  addressTag?: string;
  phoneNumber?: string;
  lat?: number;
  lng?: number;
}

interface Venue {
  id: string;
  name: string;
  cuisine?: string[];
  rating?: number;
  cost_for_two?: string;
  location?: string;
  image_url?: string;
}

export default function Dineout() {
  const [addresses, setAddresses] = useState<Address[]>([])
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [venues, setVenues] = useState<Venue[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [bookingVenue, setBookingVenue] = useState<Venue | null>(null)

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
      
      // Pass address info to search - backend can use addressId if lat/lng not available
      const data = await searchVenues(searchQuery, {
        addressId: selectedAddress.id,
        lat: selectedAddress.lat,
        lng: selectedAddress.lng
      })
      console.log('Venue search results:', data)
      console.log('Venue search results type:', typeof data)
      
      // Handle different response formats
      let venuesList = []
      if (Array.isArray(data)) {
        venuesList = data
      } else if (data.venues) {
        venuesList = data.venues
      } else if (data.restaurants) {
        venuesList = data.restaurants
      }
      
      console.log('Parsed venues:', venuesList)
      setVenues(venuesList)
    } catch (err) {
      console.error('Venue search error:', err)
      setError(err instanceof Error ? err.message : 'Search failed')
      setVenues([])
    } finally {
      setSearching(false)
    }
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
          <UtensilsCrossed className="h-8 w-8 text-primary" />
          Dineout
        </h1>
        <p className="text-muted-foreground mt-1">
          Book tables at restaurants
        </p>
      </div>

      {/* Address Selection */}
      {addresses.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <MapPin className="h-5 w-5" />
              Search Location
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
              Find restaurants to dine at or book tables
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search for restaurants, cuisines..."
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
      {venues.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold mb-4">
            Found {venues.length} venue{venues.length > 1 ? 's' : ''}
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {venues.map((venue) => (
              <Card key={venue.id} className="hover:shadow-md transition-shadow cursor-pointer">
                <CardContent className="p-4">
                  <div className="flex gap-4">
                    {venue.image_url && (
                      <div className="flex-shrink-0">
                        <img
                          src={venue.image_url}
                          alt={venue.name}
                          className="w-24 h-24 object-cover rounded-lg"
                        />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-lg truncate">{venue.name}</h3>
                      {venue.cuisine && (
                        <p className="text-sm text-muted-foreground truncate">
                          {Array.isArray(venue.cuisine) ? venue.cuisine.join(', ') : (venue.cuisine || 'Various')}
                        </p>
                      )}
                      {venue.location && (
                        <p className="text-sm text-muted-foreground truncate mt-1">
                          <MapPin className="h-3 w-3 inline mr-1" />
                          {venue.location}
                        </p>
                      )}
                      <div className="flex items-center gap-4 mt-2 text-sm">
                        {venue.rating && (
                          <span className="font-medium">⭐ {venue.rating}</span>
                        )}
                        {venue.cost_for_two && (
                          <span className="text-muted-foreground">{venue.cost_for_two}</span>
                        )}
                      </div>
                      <Button
                        size="sm"
                        className="mt-3"
                        variant="outline"
                        onClick={(e) => {
                          e.stopPropagation()
                          setBookingVenue(venue)
                        }}
                      >
                        <Clock className="h-3 w-3 mr-2" />
                        Book Table
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Booking Instructions Modal */}
      {bookingVenue && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <Card className="max-w-md w-full shadow-2xl border-primary">
            <CardHeader>
              <CardTitle className="text-xl flex items-center gap-2">
                <UtensilsCrossed className="h-5 w-5 text-primary" />
                Reserve Table at {bookingVenue.name}
              </CardTitle>
              <CardDescription>
                {Array.isArray(bookingVenue.cuisine) ? bookingVenue.cuisine.join(', ') : (bookingVenue.cuisine || 'Restaurant')}
                {bookingVenue.location ? ` • ${bookingVenue.location}` : ''}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-3 bg-secondary/50 rounded-lg text-sm space-y-2">
                <p className="font-medium">📅 Table Reservation Instructions:</p>
                <p className="text-muted-foreground">
                  Instant table reservations and Dineout deals for <strong>{bookingVenue.name}</strong> can be booked via:
                </p>
                <ul className="list-disc pl-5 text-muted-foreground space-y-1">
                  <li>The <strong>MealMind Telegram Bot</strong> (ask: &quot;Book a table at {bookingVenue.name}&quot;)</li>
                  <li>The official <strong>Swiggy Dineout App</strong></li>
                </ul>
                <p className="text-xs text-muted-foreground mt-2">
                  Web-direct table booking integration is currently in preview.
                </p>
              </div>
              <div className="flex justify-end">
                <Button onClick={() => setBookingVenue(null)}>Close</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Empty State */}
      {venues.length === 0 && searchQuery && !searching && (
        <Card>
          <CardContent className="py-12 text-center">
            <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <p className="text-muted-foreground">
              No venues found. Try a different search term or location.
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
              No addresses found. Please add an address in your Swiggy account.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
