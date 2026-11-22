/**
 * Swiggy Integration Page
 * Main dashboard for managing Swiggy ↔ MealMind synchronization
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
} from '@/components/ui/table';
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import {
  Link,
  RefreshCw,
  Truck,
  Package,
  History,
  Settings,
  AlertCircle,
  CheckCircle,
  XCircle,
  Loader2,
  Database,
  ArrowUpRight,
  ArrowDownLeft,
  Unlink,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Shield,
  Clock,
  Zap,
  Menu,
  X,
} from 'lucide-react';
import { formatDistanceToNow, parseISO, format } from 'date-fns';
import { getSwiggySyncStatus, syncOrdersFromSwiggy, getSwiggySyncHistory, disconnectSwiggy, getFoodMappings, listMealMindFoods, createMealMindFood } from '@/services/api';
import { useAuth } from '@/hooks/useAuth';

const STATUS_COLORS = {
  connected: 'bg-green-500',
  disconnected: 'bg-gray-500',
  expired: 'bg-yellow-500',
};

const SYNC_STATUS_COLORS = {
  success: 'bg-green-100 text-green-800 border-green-200',
  failed: 'bg-red-100 text-red-800 border-red-200',
  partial: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  skipped_duplicate: 'bg-blue-100 text-blue-800 border-blue-200',
};

const DIRECTION_ICONS = {
  swiggy_to_mealmind: ArrowDownLeft,
  mealmind_to_swiggy: ArrowUpRight,
};

const SyncStatusBadge = ({ status }: { status: string }) => (
  <Badge className={SYNC_STATUS_COLORS[status as keyof typeof SYNC_STATUS_COLORS] || 'bg-gray-100 text-gray-800'}>
    {status.replace('_', ' ').toUpperCase()}
  </Badge>
);

const DirectionBadge = ({ direction }: { direction: string }) => {
  const Icon = DIRECTION_ICONS[direction as keyof typeof DIRECTION_ICONS] || ArrowUpRight;
  return (
    <Badge variant="secondary" className="gap-1">
      <Icon className="h-3 w-3" />
      {direction.replace('_', ' → ')}
    </Badge>
  );
};

const SwiggyIntegration: React.FC = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  
  const [syncStatus, setSyncStatus] = useState<any>(null);
  const [syncHistory, setSyncHistory] = useState<any[]>([]);
  const [foodMappings, setFoodMappings] = useState<any[]>([]);
  const [mealMindFoods, setMealMindFoods] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [mappingsLoading, setMappingsLoading] = useState(false);
  const [foodsLoading, setFoodsLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);
  const [showFoodDialog, setShowFoodDialog] = useState(false);
  const [editingMapping, setEditingMapping] = useState<any>(null);
  const [newFood, setNewFood] = useState({
    name: '',
    canonical_name: '',
    calories_per_100g: '',
    protein_g_per_100g: '',
    carbs_g_per_100g: '',
    fat_g_per_100g: '',
    is_veg: true,
    source: 'manual',
  });

  const fetchAll = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const [statusRes, historyRes] = await Promise.all([
        getSwiggySyncStatus(),
        getSwiggySyncHistory(20, 0),
      ]);
      setSyncStatus(statusRes);
      setSyncHistory(historyRes.logs || []);
    } catch (error: any) {
      toast.error(`Failed to load sync status: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }, [user]);

  const fetchMappings = async () => {
    setMappingsLoading(true);
    try {
      const res = await getFoodMappings(100, 0);
      setFoodMappings(res.mappings || []);
    } catch (error: any) {
      toast.error(`Failed to load mappings: ${error.message}`);
    } finally {
      setMappingsLoading(false);
    }
  };

  const fetchFoods = async () => {
    setFoodsLoading(true);
    try {
      const res = await listMealMindFoods(100, 0);
      setMealMindFoods(res.foods || []);
    } catch (error: any) {
      toast.error(`Failed to load foods: ${error.message}`);
    } finally {
      setFoodsLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    if (syncStatus) {
      fetchMappings();
      fetchFoods();
    }
  }, [syncStatus]);

  const handleSyncOrders = async () => {
    if (!syncStatus) return;
    setSyncing(true);
    try {
      const addressId = prompt('Enter Swiggy address ID (or leave blank to use default):') || undefined;
      const result = await syncOrdersFromSwiggy(addressId, 100);
      toast.success(`Sync complete: ${result.new_orders} new, ${result.updated_orders} updated, ${result.skipped_duplicates} skipped`);
      fetchAll();
    } catch (error: any) {
      toast.error(`Sync failed: ${error.message}`);
    } finally {
      setSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await disconnectSwiggy();
      toast.success('Swiggy disconnected');
      fetchAll();
    } catch (error: any) {
      toast.error(`Disconnect failed: ${error.message}`);
    }
    setShowDisconnectDialog(false);
  };

  const handleCreateFood = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const payload = {
        ...newFood,
        calories_per_100g: newFood.calories_per_100g ? parseFloat(newFood.calories_per_100g) : null,
        protein_g_per_100g: newFood.protein_g_per_100g ? parseFloat(newFood.protein_g_per_100g) : null,
        carbs_g_per_100g: newFood.carbs_g_per_100g ? parseFloat(newFood.carbs_g_per_100g) : null,
        fat_g_per_100g: newFood.fat_g_per_100g ? parseFloat(newFood.fat_g_per_100g) : null,
      };
      await createMealMindFood(payload);
      toast.success('Food created');
      setShowFoodDialog(false);
      setNewFood({ name: '', canonical_name: '', calories_per_100g: '', protein_g_per_100g: '', carbs_g_per_100g: '', fat_g_per_100g: '', is_veg: true, source: 'manual' });
      fetchFoods();
    } catch (error: any) {
      toast.error(`Failed to create food: ${error.message}`);
    }
  };

  const handleUpdateMapping = async (mappingId: number, data: any) => {
    try {
      await updateFoodMapping(mappingId, data);
      toast.success('Mapping updated');
      setEditingMapping(null);
      fetchMappings();
    } catch (error: any) {
      toast.error(`Failed to update mapping: ${error.message}`);
    }
  };

  if (authLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="text-center py-12">
        <Shield className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
        <h2 className="text-xl font-semibold mb-2">Please log in to access Swiggy Integration</h2>
        <Button onClick={() => navigate('/login')}>Log In</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Swiggy Integration</h1>
          <p className="text-muted-foreground">
            Manage bidirectional synchronization between MealMind and Swiggy
          </p>
        </div>
        <div className="flex items-center gap-3">
          {syncStatus && (
            <Badge className={`gap-1 ${STATUS_COLORS[syncStatus.connection_status as keyof typeof STATUS_COLORS] || 'bg-gray-500'}`}>
              <span className="h-2 w-2 rounded-full bg-current animate-pulse" />
              {syncStatus.connection_status.charAt(0).toUpperCase() + syncStatus.connection_status.slice(1)}
            </Badge>
          )}
          <AlertDialog open={showDisconnectDialog} onOpenChange={setShowDisconnectDialog}>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="sm">
                <Unlink className="h-4 w-4 mr-2" />
                Disconnect
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Disconnect Swiggy?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will revoke your Swiggy OAuth token and stop automatic synchronization.
                  Your local order history will be preserved.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel onClick={() => setShowDisconnectDialog(false)}>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleDisconnect}>Disconnect</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* Connection Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Connection Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">
                  {syncStatus?.connection_status?.charAt(0).toUpperCase() + syncStatus?.connection_status?.slice(1) || 'Unknown'}
                </p>
                <p className="text-sm text-muted-foreground">
                  {syncStatus?.connection_status === 'connected' && syncStatus?.next_auto_sync
                    ? `Next auto-sync: ${formatDistanceToNow(parseISO(syncStatus.next_auto_sync), { addSuffix: true })}`
                    : 'Manual sync available'}
                </p>
              </div>
              <div className="text-right">
                <Button onClick={handleSyncOrders} disabled={syncing || syncStatus?.connection_status !== 'connected'}>
                  <Sync className={`h-4 w-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
                  {syncing ? 'Syncing...' : 'Sync Now'}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Orders Synced</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">{syncStatus?.total_orders_synced || 0}</p>
                <p className="text-sm text-muted-foreground">Total orders in MealMind</p>
              </div>
              <Database className="h-10 w-10 text-muted-foreground/30" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Last Order Sync</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-lg font-bold">
                  {syncStatus?.last_orders_sync
                    ? formatDistanceToNow(parseISO(syncStatus.last_orders_sync), { addSuffix: true })
                    : 'Never'}
                </p>
                <p className="text-sm text-muted-foreground">
                  {syncStatus?.last_orders_sync
                    ? format(parseISO(syncStatus.last_orders_sync), 'MMM d, yyyy HH:mm')
                    : 'No sync performed yet'}
                </p>
              </div>
              <Clock className="h-10 w-10 text-muted-foreground/30" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Failed Syncs (24h)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold text-{syncStatus?.failed_syncs_24h > 0 ? 'red' : 'green'}-600">
                  {syncStatus?.failed_syncs_24h || 0}
                </p>
                <p className="text-sm text-muted-foreground">
                  {syncStatus?.failed_syncs_24h > 0 ? 'Check sync history' : 'All clear'}
                </p>
              </div>
              <AlertCircle className="h-10 w-10 text-muted-foreground/30" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs for detailed views */}
      <Tabs defaultValue="history" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="history">Sync History</TabsTrigger>
          <TabsTrigger value="mappings">Food Mappings</TabsTrigger>
          <TabsTrigger value="foods">MealMind Foods</TabsTrigger>
          <TabsTrigger value="nutrition">Nutrition Log</TabsTrigger>
        </TabsList>

        {/* Sync History Tab */}
        <TabsContent value="history">
          <Card>
            <CardHeader>
              <CardTitle>Synchronization History</CardTitle>
              <CardDescription>
                Recent sync operations between MealMind and Swiggy
              </CardDescription>
            </CardHeader>
            <CardContent>
              {historyLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : syncHistory.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <History className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No sync history yet</p>
                  <Button variant="outline" onClick={fetchAll} className="mt-2" size="sm">
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Refresh
                  </Button>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Time</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Direction</TableHead>
                        <TableHead>External ID</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Synced / Failed</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {syncHistory.map((log) => (
                        <TableRow key={log.id}>
                          <TableCell>
                            {log.started_at ? formatDistanceToNow(parseISO(log.started_at), { addSuffix: true }) : '—'}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{log.sync_type}</Badge>
                          </TableCell>
                          <TableCell>
                            <DirectionBadge direction={log.direction} />
                          </TableCell>
                          <TableCell className="font-mono text-sm max-w-xs truncate">
                            {log.external_id}
                          </TableCell>
                          <TableCell>
                            <SyncStatusBadge status={log.status} />
                          </TableCell>
                          <TableCell>
                            <span className="text-green-600">{log.items_synced}</span> / 
                            <span className="text-red-600">{log.items_failed}</span>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Food Mappings Tab */}
        <TabsContent value="mappings">
          <Card>
            <CardHeader>
              <CardTitle>Swiggy → MealMind Food Mappings</CardTitle>
              <CardDescription>
                Map Swiggy menu items to MealMind nutrition database for automatic tracking
              </CardDescription>
            </CardHeader>
            <CardContent>
              {mappingsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : foodMappings.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Package className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No food mappings yet. Sync orders to auto-create mappings.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Swiggy Item</TableHead>
                        <TableHead>Restaurant</TableHead>
                        <TableHead>Mapped To</TableHead>
                        <TableHead>Confidence</TableHead>
                        <TableHead>Verified</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {foodMappings.map((mapping) => (
                        <TableRow key={mapping.id}>
                          <TableCell className="font-medium">{mapping.swiggy_item_name}</TableCell>
                          <TableCell className="font-mono text-sm">{mapping.swiggy_restaurant_id}</TableCell>
                          <TableCell>
                            {mapping.food ? (
                              <div>
                                <p className="font-medium">{mapping.food.name}</p>
                                <p className="text-xs text-muted-foreground">
                                  {mapping.food.calories_per_100g} kcal/100g
                                </p>
                              </div>
                            ) : (
                              <span className="text-muted-foreground">Not mapped</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2 w-32">
                              <Progress value={Math.round(mapping.confidence * 100)} className="flex-1 h-2" />
                              <span className="text-xs text-muted-foreground">{Math.round(mapping.confidence * 100)}%</span>
                            </div>
                          </TableCell>
                          <TableCell>
                            <Badge variant={mapping.verified_by_user ? 'default' : 'secondary'}>
                              {mapping.verified_by_user ? '✓ Verified' : 'Auto'}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Button variant="ghost" size="icon" onClick={() => setEditingMapping(mapping)}>
                              <Settings className="h-4 w-4" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* MealMind Foods Tab */}
        <TabsContent value="foods">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>MealMind Nutrition Database</CardTitle>
                  <CardDescription>Food items with nutrition info for tracking</CardDescription>
                </div>
                <Button onClick={() => setShowFoodDialog(true)}>
                  <Menu className="h-4 w-4 mr-2" />
                  Add Food
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {foodsLoading ? (
                <div className="flex justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-primary" />
                </div>
              ) : mealMindFoods.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Package className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>No foods in database yet. Add your first food item.</p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Calories</TableHead>
                        <TableHead>Protein</TableHead>
                        <TableHead>Carbs</TableHead>
                        <TableHead>Fat</TableHead>
                        <TableHead>Source</TableHead>
                        <TableHead>Veg</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {mealMindFoods.map((food) => (
                        <TableRow key={food.id}>
                          <TableCell className="font-medium">{food.name}</TableCell>
                          <TableCell>{food.calories_per_100g || '—'}</TableCell>
                          <TableCell>{food.protein_g_per_100g || '—'}g</TableCell>
                          <TableCell>{food.carbs_g_per_100g || '—'}g</TableCell>
                          <TableCell>{food.fat_g_per_100g || '—'}g</TableCell>
                          <TableCell>
                            <Badge variant="secondary">{food.source}</Badge>
                          </TableCell>
                          <TableCell>
                            {food.is_veg === true ? (
                              <Badge variant="default" className="bg-green-100 text-green-800">Veg</Badge>
                            ) : food.is_veg === false ? (
                              <Badge variant="default" className="bg-red-100 text-red-800">Non-Veg</Badge>
                            ) : (
                              <Badge variant="secondary">—</Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Nutrition Log Tab - placeholder */}
        <TabsContent value="nutrition">
          <Card>
            <CardHeader>
              <CardTitle>Daily Nutrition Tracking</CardTitle>
              <CardDescription>
                Log meals and track daily nutrition intake. Sync confirmed Swiggy orders to auto-populate.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-12 text-muted-foreground">
                <Zap className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p className="text-lg">Nutrition tracking coming soon</p>
                <p className="text-sm mt-2">
                  This will show daily/weekly nutrition summaries and allow logging meals from Swiggy orders
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Add Food Dialog */}
      <Dialog open={showFoodDialog} onOpenChange={setShowFoodDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Add New Food</DialogTitle>
            <DialogDescription>Add a food item to your MealMind nutrition database</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateFood} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  value={newFood.name}
                  onChange={(e) => setNewFood({ ...newFood, name: e.target.value })}
                  placeholder="e.g., Paneer Biryani"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="canonical_name">Canonical Name *</Label>
                <Input
                  id="canonical_name"
                  value={newFood.canonical_name}
                  onChange={(e) => setNewFood({ ...newFood, canonical_name: e.target.value })}
                  placeholder="e.g., paneer biryani"
                  required
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="calories">Calories/100g</Label>
                <Input
                  id="calories"
                  type="number"
                  step="0.1"
                  value={newFood.calories_per_100g}
                  onChange={(e) => setNewFood({ ...newFood, calories_per_100g: e.target.value })}
                  placeholder="250"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="protein">Protein (g/100g)</Label>
                <Input
                  id="protein"
                  type="number"
                  step="0.1"
                  value={newFood.protein_g_per_100g}
                  onChange={(e) => setNewFood({ ...newFood, protein_g_per_100g: e.target.value })}
                  placeholder="10"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="carbs">Carbs (g/100g)</Label>
                <Input
                  id="carbs"
                  type="number"
                  step="0.1"
                  value={newFood.carbs_g_per_100g}
                  onChange={(e) => setNewFood({ ...newFood, carbs_g_per_100g: e.target.value })}
                  placeholder="35"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="fat">Fat (g/100g)</Label>
                <Input
                  id="fat"
                  type="number"
                  step="0.1"
                  value={newFood.fat_per_100g}
                  onChange={(e) => setNewFood({ ...newFood, fat_per_100g: e.target.value })}
                  placeholder="8"
                />
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={newFood.is_veg}
                  onChange={(e) => setNewFood({ ...newFood, is_veg: e.target.checked })}
                />
                <span>Vegetarian</span>
              </Label>
              <Select value={newFood.source} onValueChange={(v) => setNewFood({ ...newFood, source: v })}>
                <SelectTrigger className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="swiggy">Swiggy</SelectItem>
                  <SelectItem value="usda">USDA</SelectItem>
                  <SelectItem value="openfoodfacts">OpenFoodFacts</SelectItem>
                  <SelectItem value="verified">Verified</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowFoodDialog(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!newFood.name || !newFood.canonical_name}>
                Add Food
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Mapping Dialog */}
      {editingMapping && (
        <Dialog open={true} onOpenChange={() => setEditingMapping(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Edit Mapping</DialogTitle>
              <DialogDescription>{editingMapping.swiggy_item_name}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Link to MealMind Food</Label>
                <Select
                  value={editingMapping.mealmind_food_id?.toString() || ''}
                  onValueChange={(v) => handleUpdateMapping(editingMapping.id, { mealmind_food_id: v ? parseInt(v) : null })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select food..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">None (unlink)</SelectItem>
                    {mealMindFoods.map((food) => (
                      <SelectItem key={food.id} value={food.id.toString()}>
                        {food.name} ({food.calories_per_100g || '?'} kcal/100g)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="verified"
                  checked={editingMapping.verified_by_user}
                  onChange={(e) => handleUpdateMapping(editingMapping.id, { verified_by_user: e.target.checked })}
                />
                <Label htmlFor="verified">Mark as verified by user</Label>
              </div>
              <div className="space-y-2">
                <Label>Confidence: {Math.round(editingMapping.confidence * 100)}%</Label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={Math.round(editingMapping.confidence * 100)}
                  onChange={(e) => handleUpdateMapping(editingMapping.id, { confidence: parseInt(e.target.value) / 100 })}
                  className="w-full"
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingMapping(null)}>
                Close
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
};

export default SwiggyIntegration;