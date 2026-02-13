import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';
import {
  QAPair,
  QAPairReviewStatus,
  REVIEW_STATUS_COLORS,
  ChatMessage,
} from '@/types/training-data';
import {
  CheckCircle,
  XCircle,
  AlertCircle,
  Edit,
  Loader2,
  User,
  Bot,
  Settings,
  Wrench,
} from 'lucide-react';

interface QAPairReviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pair: QAPair;
  onSaved: () => void;
  canEdit: boolean;
}

// Message role icons
const roleIcons: Record<string, React.ReactNode> = {
  system: <Settings className="h-4 w-4" />,
  user: <User className="h-4 w-4" />,
  assistant: <Bot className="h-4 w-4" />,
  tool: <Wrench className="h-4 w-4" />,
};

// Message role colors
const roleColors: Record<string, string> = {
  system: 'bg-gray-100 border-gray-300',
  user: 'bg-blue-50 border-blue-200',
  assistant: 'bg-green-50 border-green-200',
  tool: 'bg-yellow-50 border-yellow-200',
};

export default function QAPairReviewDialog({
  open,
  onOpenChange,
  pair,
  onSaved,
  canEdit,
}: QAPairReviewDialogProps) {
  const { post, put } = useApi();
  const { toast } = useToast();

  const [reviewNotes, setReviewNotes] = useState(pair.review_notes || '');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editedMessages, setEditedMessages] = useState<ChatMessage[]>(pair.messages);

  // Reset state when pair changes
  React.useEffect(() => {
    setReviewNotes(pair.review_notes || '');
    setEditedMessages(pair.messages);
    setIsEditing(false);
  }, [pair]);

  const handleReview = async (status: QAPairReviewStatus) => {
    setIsSubmitting(true);
    try {
      const payload: {
        review_status: QAPairReviewStatus;
        review_notes?: string;
        messages?: ChatMessage[];
      } = {
        review_status: status,
        review_notes: reviewNotes || undefined,
      };

      // If editing, include edited messages
      if (isEditing && JSON.stringify(editedMessages) !== JSON.stringify(pair.messages)) {
        payload.messages = editedMessages;
      }

      const response = await post(`/api/training-data/pairs/${pair.id}/review`, payload);

      if (response.error) {
        throw new Error(response.error);
      }

      toast({
        title: 'Review saved',
        description: `Pair marked as ${status}`,
      });

      onSaved();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save review';
      toast({ variant: 'destructive', title: 'Error', description: message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleMessageEdit = (index: number, content: string) => {
    setEditedMessages(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], content };
      return updated;
    });
  };

  const renderMessage = (message: ChatMessage, index: number) => {
    const colorClass = roleColors[message.role] || 'bg-gray-50 border-gray-200';
    const icon = roleIcons[message.role] || <User className="h-4 w-4" />;

    return (
      <div key={index} className={`rounded-lg border p-4 ${colorClass}`}>
        <div className="flex items-center gap-2 mb-2">
          {icon}
          <span className="font-medium capitalize">{message.role}</span>
          {message.name && (
            <span className="text-sm text-muted-foreground">({message.name})</span>
          )}
        </div>
        {isEditing && canEdit && message.role !== 'system' ? (
          <Textarea
            value={editedMessages[index]?.content || message.content}
            onChange={(e) => handleMessageEdit(index, e.target.value)}
            className="min-h-[100px] bg-white"
          />
        ) : (
          <div className="whitespace-pre-wrap text-sm">{message.content}</div>
        )}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-2 text-xs text-muted-foreground">
            <span className="font-medium">Tool calls:</span>{' '}
            {message.tool_calls.length} call(s)
          </div>
        )}
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Review QA Pair
            <Badge className={REVIEW_STATUS_COLORS[pair.review_status] || 'bg-gray-100'}>
              {pair.review_status.replace('_', ' ')}
            </Badge>
            {pair.was_auto_approved && (
              <Badge variant="outline">Auto-approved</Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            Review and optionally edit this question-answer pair before approving.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="conversation" className="w-full">
          <TabsList>
            <TabsTrigger value="conversation">Conversation</TabsTrigger>
            <TabsTrigger value="metadata">Metadata</TabsTrigger>
            {pair.original_messages && (
              <TabsTrigger value="original">Original</TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="conversation" className="mt-4">
            <ScrollArea className="h-[400px] pr-4">
              <div className="space-y-4">
                {(isEditing ? editedMessages : pair.messages).map((msg, idx) => renderMessage(msg, idx))}
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="metadata" className="mt-4">
            <div className="grid grid-cols-2 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Quality</CardTitle>
                </CardHeader>
                <CardContent>
                  {pair.quality_score !== null && pair.quality_score !== undefined ? (
                    <div className="text-2xl font-bold">
                      {(pair.quality_score * 100).toFixed(0)}%
                    </div>
                  ) : (
                    <span className="text-muted-foreground">Not scored</span>
                  )}
                  {pair.quality_flags && pair.quality_flags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {pair.quality_flags.map((flag, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          {flag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Split Assignment</CardTitle>
                </CardHeader>
                <CardContent>
                  {pair.split ? (
                    <Badge>{pair.split}</Badge>
                  ) : (
                    <span className="text-muted-foreground">Not assigned</span>
                  )}
                  <div className="text-sm mt-2">
                    Weight: {pair.sampling_weight}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Source</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-sm">
                    <span className="text-muted-foreground">Item ref:</span>{' '}
                    {pair.source_item_ref || 'None'}
                  </div>
                  {pair.canonical_label_id && (
                    <div className="text-sm mt-1">
                      <span className="text-muted-foreground">Canonical label:</span>{' '}
                      <span className="font-mono text-xs">{pair.canonical_label_id}</span>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Semantic Concepts</CardTitle>
                </CardHeader>
                <CardContent>
                  {pair.semantic_concept_iris && pair.semantic_concept_iris.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {pair.semantic_concept_iris.map((iri, idx) => (
                        <Badge key={idx} variant="outline" className="text-xs">
                          {iri.split('/').pop() || iri}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <span className="text-muted-foreground">No concepts linked</span>
                  )}
                </CardContent>
              </Card>
            </div>

            {pair.generation_metadata && (
              <Card className="mt-4">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm">Generation Metadata</CardTitle>
                </CardHeader>
                <CardContent>
                  <pre className="text-xs bg-muted p-2 rounded overflow-auto max-h-[200px]">
                    {JSON.stringify(pair.generation_metadata, null, 2)}
                  </pre>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {pair.original_messages && (
            <TabsContent value="original" className="mt-4">
              <ScrollArea className="h-[400px] pr-4">
                <div className="space-y-4">
                  {pair.original_messages.map((msg, idx) => (
                    <div key={idx} className={`rounded-lg border p-4 ${roleColors[msg.role]}`}>
                      <div className="flex items-center gap-2 mb-2">
                        {roleIcons[msg.role]}
                        <span className="font-medium capitalize">{msg.role}</span>
                      </div>
                      <div className="whitespace-pre-wrap text-sm">{msg.content}</div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
              {pair.edit_distance !== undefined && (
                <div className="mt-2 text-sm text-muted-foreground">
                  Edit distance from original: {pair.edit_distance}
                </div>
              )}
            </TabsContent>
          )}
        </Tabs>

        {/* Review Notes */}
        <div className="space-y-2">
          <Label>Review Notes</Label>
          <Textarea
            placeholder="Add notes about this review..."
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
            disabled={!canEdit}
          />
        </div>

        <DialogFooter className="flex items-center justify-between sm:justify-between">
          <div className="flex items-center gap-2">
            {canEdit && (
              <Button
                variant="outline"
                onClick={() => setIsEditing(!isEditing)}
                disabled={isSubmitting}
              >
                <Edit className="mr-2 h-4 w-4" />
                {isEditing ? 'Cancel Edit' : 'Edit Messages'}
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Close
            </Button>
            {canEdit && (
              <>
                <Button
                  variant="outline"
                  onClick={() => handleReview(QAPairReviewStatus.FLAGGED)}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <AlertCircle className="mr-2 h-4 w-4" />
                  )}
                  Flag
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => handleReview(QAPairReviewStatus.REJECTED)}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <XCircle className="mr-2 h-4 w-4" />
                  )}
                  Reject
                </Button>
                <Button
                  onClick={() => handleReview(isEditing ? QAPairReviewStatus.EDITED : QAPairReviewStatus.APPROVED)}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle className="mr-2 h-4 w-4" />
                  )}
                  {isEditing ? 'Save & Approve' : 'Approve'}
                </Button>
              </>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
