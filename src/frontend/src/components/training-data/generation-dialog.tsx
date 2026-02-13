import React from 'react';
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
import { Checkbox } from '@/components/ui/checkbox';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { GenerationRequest } from '@/types/training-data';
import { Loader2, Sparkles } from 'lucide-react';

const generationFormSchema = z.object({
  sample_size: z.number().min(1).max(10000).default(100),
  model: z.string().optional(),
  temperature: z.number().min(0).max(2).optional(),
  max_tokens: z.number().min(1).max(8192).optional(),
  auto_approve_with_canonical: z.boolean().default(true),
  link_to_canonical: z.boolean().default(true),
});

type GenerationFormValues = z.infer<typeof generationFormSchema>;

interface GenerationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  collectionId: string;
  onGenerate: (request: GenerationRequest) => Promise<void>;
}

export default function GenerationDialog({
  open,
  onOpenChange,
  collectionId,
  onGenerate,
}: GenerationDialogProps) {
  const [isGenerating, setIsGenerating] = React.useState(false);

  const form = useForm<GenerationFormValues>({
    resolver: zodResolver(generationFormSchema),
    defaultValues: {
      sample_size: 100,
      model: '',
      temperature: 0.7,
      max_tokens: 1024,
      auto_approve_with_canonical: true,
      link_to_canonical: true,
    },
  });

  const onSubmit = async (values: GenerationFormValues) => {
    setIsGenerating(true);
    try {
      const request: GenerationRequest = {
        collection_id: collectionId,
        sample_size: values.sample_size,
        model: values.model || undefined,
        temperature: values.temperature,
        max_tokens: values.max_tokens,
        auto_approve_with_canonical: values.auto_approve_with_canonical,
        link_to_canonical: values.link_to_canonical,
      };
      await onGenerate(request);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5" />
            Generate QA Pairs
          </DialogTitle>
          <DialogDescription>
            Generate question-answer pairs from the sheet data using the configured template.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="sample_size"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Sample Size</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={1}
                      max={10000}
                      {...field}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 100)}
                    />
                  </FormControl>
                  <FormDescription>
                    Number of items to sample from the sheet
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="model"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Model (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g., gpt-4 (uses template default)" {...field} />
                  </FormControl>
                  <FormDescription>
                    Override the template's default model
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="temperature"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Temperature</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        step={0.1}
                        min={0}
                        max={2}
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
                name="max_tokens"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max Tokens</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={8192}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value))}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="auto_approve_with_canonical"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>Auto-approve with canonical</FormLabel>
                    <FormDescription>
                      Auto-approve pairs that match existing canonical labels
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="link_to_canonical"
              render={({ field }) => (
                <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="space-y-1 leading-none">
                    <FormLabel>Link to canonical labels</FormLabel>
                    <FormDescription>
                      Link generated pairs to canonical labels for reuse tracking
                    </FormDescription>
                  </div>
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={isGenerating}>
                {isGenerating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    Generate
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
