import React, { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { useApi } from '@/hooks/use-api';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import {
  TrainingCollection,
  TrainingCollectionCreate,
  TrainingCollectionStatus,
  GenerationMethod,
  Sheet,
  PromptTemplate,
} from '@/types/training-data';

// Form schema with Zod validation
const collectionFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255, 'Name must be 255 characters or less'),
  description: z.string().optional(),
  version: z.string().default('1.0.0'),
  status: z.nativeEnum(TrainingCollectionStatus).default(TrainingCollectionStatus.DRAFT),
  sheet_id: z.string().optional(),
  template_id: z.string().optional(),
  generation_method: z.nativeEnum(GenerationMethod).default(GenerationMethod.LLM),
  model_used: z.string().optional(),
  default_train_ratio: z.number().min(0).max(1).default(0.8),
  default_val_ratio: z.number().min(0).max(1).default(0.1),
  default_test_ratio: z.number().min(0).max(1).default(0.1),
  tags: z.array(z.string()).default([]),
});

type CollectionFormValues = z.infer<typeof collectionFormSchema>;

interface TrainingCollectionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collection?: TrainingCollection | null;
  sheets: Sheet[];
  templates: PromptTemplate[];
  onSaved: (collection: TrainingCollection) => void;
}

export default function TrainingCollectionFormDialog({
  open,
  onOpenChange,
  collection,
  sheets,
  templates,
  onSaved,
}: TrainingCollectionFormDialogProps) {
  const { post, put } = useApi();
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = React.useState(false);

  const isEditing = !!collection;

  const form = useForm<CollectionFormValues>({
    resolver: zodResolver(collectionFormSchema),
    defaultValues: {
      name: '',
      description: '',
      version: '1.0.0',
      status: TrainingCollectionStatus.DRAFT,
      sheet_id: undefined,
      template_id: undefined,
      generation_method: GenerationMethod.LLM,
      model_used: '',
      default_train_ratio: 0.8,
      default_val_ratio: 0.1,
      default_test_ratio: 0.1,
      tags: [],
    },
  });

  // Reset form when dialog opens/closes or collection changes
  useEffect(() => {
    if (open && collection) {
      form.reset({
        name: collection.name,
        description: collection.description || '',
        version: collection.version,
        status: collection.status,
        sheet_id: collection.sheet_id || undefined,
        template_id: collection.template_id || undefined,
        generation_method: collection.generation_method,
        model_used: collection.model_used || '',
        default_train_ratio: collection.default_train_ratio,
        default_val_ratio: collection.default_val_ratio,
        default_test_ratio: collection.default_test_ratio,
        tags: collection.tags || [],
      });
    } else if (open && !collection) {
      form.reset({
        name: '',
        description: '',
        version: '1.0.0',
        status: TrainingCollectionStatus.DRAFT,
        sheet_id: undefined,
        template_id: undefined,
        generation_method: GenerationMethod.LLM,
        model_used: '',
        default_train_ratio: 0.8,
        default_val_ratio: 0.1,
        default_test_ratio: 0.1,
        tags: [],
      });
    }
  }, [open, collection, form]);

  const onSubmit = async (values: CollectionFormValues) => {
    setIsSubmitting(true);
    try {
      const payload: TrainingCollectionCreate = {
        name: values.name,
        description: values.description || undefined,
        version: values.version,
        status: values.status,
        sheet_id: values.sheet_id || undefined,
        template_id: values.template_id || undefined,
        generation_method: values.generation_method,
        model_used: values.model_used || undefined,
        default_train_ratio: values.default_train_ratio,
        default_val_ratio: values.default_val_ratio,
        default_test_ratio: values.default_test_ratio,
        tags: values.tags,
      };

      let response;
      if (isEditing && collection) {
        response = await put<TrainingCollection>(`/api/training-data/collections/${collection.id}`, payload);
      } else {
        response = await post<TrainingCollection>('/api/training-data/collections', payload);
      }

      if (response.error) {
        throw new Error(response.error);
      }

      onSaved(response.data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to save collection';
      toast({
        variant: 'destructive',
        title: 'Error',
        description: message,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'Edit Collection' : 'Create Training Collection'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update the training collection details.'
              : 'Create a new training collection to organize QA pairs for model fine-tuning.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Basic Info */}
            <div className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Customer Support QA v1" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Describe the purpose and scope of this training collection..."
                        rows={3}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="version"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Version</FormLabel>
                      <FormControl>
                        <Input placeholder="1.0.0" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="status"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Status</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select status" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={TrainingCollectionStatus.DRAFT}>Draft</SelectItem>
                          <SelectItem value={TrainingCollectionStatus.GENERATING}>Generating</SelectItem>
                          <SelectItem value={TrainingCollectionStatus.REVIEW}>Review</SelectItem>
                          <SelectItem value={TrainingCollectionStatus.APPROVED}>Approved</SelectItem>
                          <SelectItem value={TrainingCollectionStatus.EXPORTED}>Exported</SelectItem>
                          <SelectItem value={TrainingCollectionStatus.ARCHIVED}>Archived</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Data Source */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Data Source</h3>
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="sheet_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Sheet</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value || ''}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a sheet" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="">None</SelectItem>
                          {sheets.map((sheet) => (
                            <SelectItem key={sheet.id} value={sheet.id}>
                              {sheet.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        The data sheet containing source items
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="template_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Template</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value || ''}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a template" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="">None</SelectItem>
                          {templates.filter(t => t.status === 'active').map((template) => (
                            <SelectItem key={template.id} value={template.id}>
                              {template.name} (v{template.version})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        The prompt template for QA generation
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Generation Settings */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Generation Settings</h3>
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="generation_method"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Generation Method</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select method" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={GenerationMethod.LLM}>LLM</SelectItem>
                          <SelectItem value={GenerationMethod.MANUAL}>Manual</SelectItem>
                          <SelectItem value={GenerationMethod.HYBRID}>Hybrid</SelectItem>
                          <SelectItem value={GenerationMethod.IMPORTED}>Imported</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="model_used"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Model</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., gpt-4" {...field} />
                      </FormControl>
                      <FormDescription>
                        Model used for generation
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Split Ratios */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Default Split Ratios</h3>
              <div className="grid grid-cols-3 gap-4">
                <FormField
                  control={form.control}
                  name="default_train_ratio"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Train</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.05"
                          min="0"
                          max="1"
                          {...field}
                          onChange={(e) => field.onChange(parseFloat(e.target.value))}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="default_val_ratio"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Validation</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.05"
                          min="0"
                          max="1"
                          {...field}
                          onChange={(e) => field.onChange(parseFloat(e.target.value))}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="default_test_ratio"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Test</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          step="0.05"
                          min="0"
                          max="1"
                          {...field}
                          onChange={(e) => field.onChange(parseFloat(e.target.value))}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isEditing ? 'Save Changes' : 'Create Collection'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
