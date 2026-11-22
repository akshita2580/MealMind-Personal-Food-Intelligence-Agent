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
  RefreshCw,
  Package,
  History,
  Settings,
  AlertCircle,
  Loader2,
  Database,
  ArrowUpRight,
  ArrowDownLeft,
  Unlink,
  Shield,
  Clock,
  Zap,
  Menu,
  RefreshCcw,
} from 'lucide-react';
import { formatDistanceToNow, parseISO, format } from 'date-fns';
import { getSwiggySyncStatus, syncOrdersFromSwiggy, getSwiggySyncHistory, disconnectSwiggy } from '@/services/api';
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
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [showDisconnectDialog, setShowDisconnectDialog] = useState(false);

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

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleSyncOrders = async () => {
    if (!syncStatus) return;
    setSyncing(true);
    try {
      const result = await syncOrdersFromSwiggy(undefined, 100);
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
                  <RefreshCcw className={`h-4 w-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
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
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="history">Sync History</TabsTrigger>
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
              {loading ? (
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
    </div>
  );
};

export default SwiggyIntegration;
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